from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from engine.admin_units import ParentRow
from engine.schema import AdministrativeUnit


@dataclass
class ValidationError:
    code: str
    message: str


def validate_page_count(expected: int, extracted: int) -> list[ValidationError]:
    if expected <= 0:
        return [ValidationError(code="pdfinfo_failed", message="page count unavailable")]
    if extracted <= 0:
        return [ValidationError(code="text_extraction_failed", message="no pages extracted")]
    if abs(expected - extracted) > 2:
        return [
            ValidationError(
                code="page_count_mismatch",
                message=f"expected {expected}, extracted {extracted}",
            )
        ]
    return []


def validate_admin_unit_codes(units: Iterable[AdministrativeUnit]) -> list[ValidationError]:
    seen = set()
    duplicates = []
    for unit in units:
        code = unit.unit_code.value
        table_type = unit.table_type
        if not code:
            continue
        key = (table_type, code)
        if key in seen:
            duplicates.append(code)
        else:
            seen.add(key)
    if duplicates:
        return [
            ValidationError(
                code="duplicate_admin_unit",
                message=f"duplicate admin unit codes: {sorted(set(duplicates))}",
            )
        ]
    return []


def validate_mda_reconciliation(
    parent_rows: Iterable[ParentRow],
    units: Iterable[AdministrativeUnit],
) -> list[ValidationError]:
    tolerance = 1.0
    unit_sums: dict[tuple[str, str], dict[str, float]] = {}

    for unit in units:
        if unit.table_type != "expenditure_mda":
            continue
        parent_code = unit.parent_code.value
        if not parent_code:
            continue
        key = (unit.table_type, parent_code)
        if key not in unit_sums:
            unit_sums[key] = {}
        for item in unit.amounts:
            if item.amount.value is None:
                continue
            unit_sums[key][item.label] = unit_sums[key].get(item.label, 0.0) + float(
                item.amount.value
            )

    errors: list[ValidationError] = []
    for parent in parent_rows:
        if parent.table_type != "expenditure_mda":
            continue
        key = (parent.table_type, parent.code)
        if key not in unit_sums:
            continue
        for item in parent.amounts:
            expected = item.amount.value
            if expected is None:
                continue
            actual = unit_sums[key].get(item.label)
            if actual is None:
                continue
            if abs(expected - actual) > tolerance:
                errors.append(
                    ValidationError(
                        code="mda_reconciliation_failed",
                        message=(
                            f"parent {parent.code} {item.label} expected {expected} "
                            f"got {round(actual, 2)}"
                        ),
                    )
                )

    return errors
