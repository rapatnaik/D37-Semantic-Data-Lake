"""Discovery checks use only synthetic temporary directories and fixtures."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agents.investigator import discover
from examples.investigator_starter import FIXTURE_ROOT, run_example


class DiscoveryTests(unittest.TestCase):
    def test_stable_ids_and_sorted_recursive_inventory(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            roots = [Path(first), Path(second)]
            for root in roots:
                (root / 'nested').mkdir()
                (root / 'nested/z.csv').write_text('age\n25\n')
                (root / 'b.txt').write_text('notes')
            initial = discover(roots[0])
            self.assertEqual(initial, discover(roots[0]))
            relocated = discover(roots[1])
            self.assertEqual([s.source_id for s in initial.sources], [s.source_id for s in relocated.sources])
            self.assertEqual(initial.components, relocated.components)
            (roots[0] / 'a.csv').write_text('age\n30\n')
            (roots[0] / 'nested/z.csv').write_text('age\n25\n40\n')
            updated = discover(roots[0])
            self.assertEqual([s.relative_path for s in updated.sources], ['a.csv', 'b.txt', 'nested/z.csv'])
            self.assertEqual(initial.components, updated.components[1:])
            self.assertNotEqual(initial.sources[-1].size_bytes, updated.sources[-1].size_bytes)

    def test_exclusions_and_symlinks_never_opened(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as outside:
            root = Path(folder)
            for name in ('.env', 'credentials.json', 'secret.txt', 'id_rsa', 'private.key'):
                (root / name).write_text('do not inspect')
            for name in ('.git', '.aws', '.d37-agent', 'node_modules'):
                (root / name).mkdir()
                (root / name / 'data.csv').write_text('do not inspect')
            target = Path(outside) / 'outside.csv'
            target.write_text('outside')
            (root / 'external.csv').symlink_to(target)
            (root / 'external-dir').symlink_to(outside, target_is_directory=True)
            (root / 'broken.csv').symlink_to(root / 'missing')
            (root / 'loop').symlink_to(root, target_is_directory=True)
            # No file in this directory is eligible for prefix inspection.
            with patch.object(Path, 'open', side_effect=AssertionError('excluded file opened')):
                inventory = discover(root)
            self.assertEqual(inventory.sources, [])

    def test_format_candidates_and_unsupported_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            samples = {
                'a.csv': (b'age\n20\n', 'csv', 'table'),
                'b.bin': (b'\x89PNG\r\n\x1a\n', 'png', 'images'),
                'c.pdf': (b'%PDF-1.7', 'pdf', 'documents'),
                'd.xlsx': (b'PK\x03\x04', 'zip', 'unknown'),
                'e.csv': (b'\x00\xff', 'unknown', 'unknown'),
                'f.py': (b'raise RuntimeError("never execute")', 'unknown', 'unknown'),
            }
            for name, (data, _, _) in samples.items():
                (root / name).write_bytes(data)
            inventory = discover(root)
            for source, component in zip(inventory.sources, inventory.components):
                _, expected_format, expected_kind = samples[source.relative_path]
                self.assertEqual(source.format, expected_format)
                self.assertEqual(component.kind, expected_kind)
                self.assertEqual(component.selector, {})
                self.assertEqual(component.source_ids, [source.source_id])
            self.assertTrue(any('d.xlsx' in entry for entry in inventory.limitations))

    def test_unreadable_file_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'data.csv').write_text('age\n20\n')
            with patch.object(Path, 'open', side_effect=PermissionError):
                inventory = discover(folder)
            self.assertEqual(inventory.sources[0].format, 'unknown')
            self.assertTrue(any('PermissionError' in entry for entry in inventory.limitations))

    def test_fixture_measurements_and_preservation(self):
        paths = list(FIXTURE_ROOT.iterdir())
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
        inventory, result = run_example()
        result.validate_references(inventory)
        self.assertEqual(result.measurements, {'row_count': 10, 'columns': {'age': {'null_count': 2}}})
        self.assertEqual((result.coverage.mode, result.coverage.unit,
                          result.coverage.examined, result.coverage.total), ('full', 'rows', 10, 10))
        self.assertEqual(before, {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths})

    def test_invalid_root(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'file.csv'
            path.write_text('a')
            with self.assertRaises(NotADirectoryError):
                discover(path)
            with self.assertRaises(FileNotFoundError):
                discover(Path(folder) / 'missing')
