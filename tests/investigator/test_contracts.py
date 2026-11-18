"""Persistent checks for the shared public interfaces."""

import unittest

from agents.investigator.contracts import (
    AnalysisRequest, ArtifactRef, ComponentRef, Coverage, Inventory, SourceRef, ToolResult,
)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.source = SourceRef('s', 'patients.csv', 'csv', 20, 1)
        self.component = ComponentRef('c', 'table', ['s'])
        self.inventory = Inventory([self.source], [self.component])
        self.coverage = Coverage('full', 'rows', 10, 10, 'all rows')
        self.artifact = ArtifactRef('a', 'plots/age.png', 'image/png')
        self.result = ToolResult('r', 'c', 'complete', ['s'], 'count', {}, self.coverage,
                                 {'columns': {'age': {'null_count': 2}}}, [self.artifact])

    def test_all_contract_round_trips(self):
        request = AnalysisRequest('Count rows', 'pass', ['s'], {'seed': 42}, ['application/json'])
        for value in (self.source, self.component, self.inventory, self.coverage,
                      self.artifact, self.result, request):
            with self.subTest(contract=type(value).__name__):
                decoded = type(value).from_json(value.to_json())
                self.assertEqual(decoded, value)
                self.assertEqual(type(decoded), type(value))
        self.assertIsInstance(ToolResult.from_json(self.result.to_json()).coverage, Coverage)
        self.assertIsInstance(Inventory.from_json(self.inventory.to_json()).sources[0], SourceRef)

    def test_invalid_constructors(self):
        factories = [
            lambda: SourceRef('s', '../data.csv', 'csv', 0, 0),
            lambda: SourceRef('s', '/data.csv', 'csv', 0, 0),
            lambda: SourceRef('s', 'data.csv', 'csv', True, 0),
            lambda: Coverage('full', 'rows', 9, 10, 'all'),
            lambda: Coverage('sample', 'rows', 11, 10, 'sample'),
            lambda: Coverage('none', 'rows', 1, None, 'none'),
            lambda: ComponentRef('c', 'table', []),
            lambda: Inventory([self.source, self.source], []),
            lambda: Inventory([self.source], [ComponentRef('c', 'table', ['missing'])]),
            lambda: ArtifactRef('a', '../plot.png', 'image/png'),
            lambda: AnalysisRequest('q', 'pass', ['s'], {}, []),
            lambda: ToolResult('r', 'c', 'failed', ['s'], 'count', {}, self.coverage, {}),
        ]
        for index, factory in enumerate(factories):
            with self.subTest(case=index), self.assertRaises(ValueError):
                factory()

    def test_decode_rejects_invalid_json_objects(self):
        for raw in ('{"source_id":"s","source_id":"t"}', '{"extra":1}', '[]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                SourceRef.from_json(raw)

    def test_mutation_is_revalidated(self):
        self.result.measurements['bad'] = float('nan')
        with self.assertRaises(ValueError):
            self.result.to_json()
        del self.result.measurements['bad']
        self.coverage.examined = 11
        with self.assertRaises(ValueError):
            self.result.to_json()

    def test_reference_validation(self):
        self.result.validate_references(self.inventory)
        self.result.component_id = 'missing'
        with self.assertRaises(ValueError):
            self.result.validate_references(self.inventory)
        self.result.component_id = 'c'
        self.result.inputs = ['missing']
        with self.assertRaises(ValueError):
            self.result.validate_references(self.inventory)
        other = SourceRef('other', 'other.csv', 'csv', 0, 0)
        self.inventory.sources.append(other)
        self.result.inputs = ['other']
        with self.assertRaises(ValueError):
            self.result.validate_references(self.inventory)
