"""Disposable interface example, not the production table profiler."""

import csv
from pathlib import Path

from agents.investigator import discover
from agents.investigator.contracts import Coverage, Inventory, ToolResult

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / 'tests/investigator/fixtures'


def run_example() -> tuple[Inventory, ToolResult]:
    inventory = discover(FIXTURE_ROOT)
    source = next(item for item in inventory.sources if item.relative_path == 'patients.csv')
    component = next(item for item in inventory.components if source.source_id in item.source_ids)
    path = (FIXTURE_ROOT / source.relative_path).resolve(strict=True)
    if not path.is_relative_to(FIXTURE_ROOT.resolve()):
        raise ValueError('Example source is outside the fixture root')
    with path.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    missing = sum(row['age'].strip() == '' for row in rows)
    result = ToolResult(
        result_id='example_patients_counts',
        component_id=component.component_id,
        status='complete',
        inputs=[source.source_id],
        method='example_csv_counts',
        parameters={'missing_age_definition': 'empty or whitespace-only age'},
        coverage=Coverage('full', 'rows', len(rows), len(rows), 'all data rows, excluding header'),
        measurements={'row_count': len(rows), 'columns': {'age': {'null_count': missing}}},
        limitations=['Example only: counts rows and blank ages; no type inference or production profiling.'],
    )
    result.validate_references(inventory)
    return inventory, result


if __name__ == '__main__':
    _, result = run_example()
    print(result.to_json(), end='')
