"""Read-only, bounded discovery; format labels are candidates, not profiles."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .contracts import ComponentRef, Inventory, SourceRef

from zipfile import ZipFile, BadZipFile

_PREFIX_BYTES = 4096

def _id(prefix: str, value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True).encode()
    return prefix + hashlib.sha256(encoded).hexdigest()


def _excluded(name: str) -> bool:
    lower = name.lower()
    return (
        lower.startswith('.')
        or lower in {'__pycache__', 'node_modules', 'credentials', 'secrets', 'env', 'venv','output','outputs'}
        or any(word in lower for word in ('credential', 'secret', 'token', 'password'))
        or lower.startswith(('id_rsa', 'id_ed25519', 'id_ecdsa'))
        or Path(lower).suffix in {'.pem', '.key', '.p12', '.pfx', '.keystore'}
    )


def _identify_zip(path: Path) -> tuple[str, str]:
    # Classify Office ZIP file into Document or Excel table without extracting files
    try:
        with ZipFile(path) as archive:
            names = set(archive.namelist())

            if 'xl/workbook.xml' in names:
                return 'xlsx', 'table'
            if 'word/document.xml' in names:
                return 'docx', 'documents'
    except (BadZipFile, OSError, ValueError):
        pass

    return 'zip', 'unknown'


def _identify(path: Path, prefix: bytes) -> tuple[str, str]:
    for signature, format_name in (
        (b'\x89PNG\r\n\x1a\n', 'png'), (b'\xff\xd8\xff', 'jpeg'),
        (b'II*\x00', 'tiff'), (b'MM\x00*', 'tiff'),
        (b'II+\x00', 'tiff'), (b'MM\x00+', 'tiff'),
    ):
        if prefix.startswith(signature):
            return format_name, 'images'
    if prefix.startswith(b'PAR1'):
        return 'parquet', 'table'
    if prefix.startswith(b'%PDF-'):
        return 'pdf', 'documents'
    # ZIP containers could be Excel/DOCX, but require a dedicated reader.
    if prefix.startswith(b'PK\x03\x04'):
        return _identify_zip(path)
    try:
        prefix.decode('utf-8-sig', errors='strict')
        text_like = b'\x00' not in prefix
    except UnicodeDecodeError:
        text_like = False
    suffix = path.suffix.lower()
    if text_like and suffix in {'.csv', '.tsv', '.json', '.jsonl'}:
        return suffix[1:], 'table'
    if text_like and suffix in {'.txt', '.md'}:
        return suffix[1:], 'documents'
    return 'unknown', 'unknown'



def discover(root: str | Path) -> Inventory:
    """Inventory a directory in relative-path order without following symlinks.

    Exclusions are filename-based, not a guarantee of secret-content detection.
    Use an explicitly selected data directory, not an arbitrary home directory.
    This starter is not a sandbox against concurrent filesystem replacement.
    """
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)
    sources: list[SourceRef] = []
    components: list[ComponentRef] = []
    limitations = [
        'Format labels are candidates, not validated file contents.',
        'Discovery uses file signatures, extensions, and bounded prefix reads; parsing is handled by downstream tools.',
        'ZIP-based Office formats are identified by internal filenames, not by validating workbook or document content.',
        'No Excel sheets, image pixels, document contents, or collection associations are inspected.',
        'Hidden entries, common credential names, caches, generated output directories, and symlinks are excluded.',
        'Filename exclusions cannot detect arbitrary secrets stored inside otherwise eligible files.',
        'Discovery is read-only but is not a complete sandbox against concurrent filesystem changes.',
    ]


    def walk_error(error: OSError) -> None:
        # Do not leak absolute dataset roots through error messages.
        limitations.append('A directory could not be listed: ' + type(error).__name__)

    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        parent = Path(directory)
        dirs[:] = sorted(name for name in dirs if not _excluded(name) and not (parent / name).is_symlink())
        for name in sorted(files):
            path = parent / name
            if _excluded(name) or path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            if any(char in relative for char in ('\\', ':', '\x00')):
                limitations.append(f'Unrepresentable source path skipped: {relative!r}')
                continue
            try:
                if not path.resolve(strict=True).is_relative_to(root) or not path.is_file():
                    limitations.append(f'Non-regular or outside-root input skipped: {relative}')
                    continue
                stat = path.stat()
            except OSError as error:
                limitations.append(f'Cannot stat {relative}: {type(error).__name__}')
                continue
            try:
                with path.open('rb') as handle:
                    format_name, kind = _identify(path, handle.read(_PREFIX_BYTES))
            except OSError as error:
                format_name, kind = 'unknown', 'unknown'
                limitations.append(f'Cannot inspect {relative}: {type(error).__name__}')
            source_id = _id('source_', relative)
            source = SourceRef(source_id, relative, format_name, stat.st_size, stat.st_mtime_ns)
            sources.append(source)
            components.append(ComponentRef(_id('component_', [source_id, {}]), kind, [source_id]))
            if kind == 'unknown':
                limitations.append(f'Unsupported input retained without analysis: {relative}')
    sources.sort(key=lambda source: source.relative_path)
    order = {source.source_id: index for index, source in enumerate(sources)}
    components.sort(key=lambda component: order[component.source_ids[0]])
    return Inventory(sources, components, sorted(limitations))
