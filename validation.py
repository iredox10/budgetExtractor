from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from engine.admin_units import ParentRow
from engine.economic import EconomicConflict
from engine.schema import AdministrativeUnit, EconomicExpenditureRow, RevenueRow


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


def validate_economic_rows(
    revenue_rows: Iterable[RevenueRow],
    expenditure_rows: Iterable[EconomicExpenditureRow],
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for row in revenue_rows:
        if row.amount.value is None:
            errors.append(
                ValidationError(
                    code="economic_amount_missing",
                    message=f"revenue row missing amount: {row.line_text}",
                )
            )
    for row in expenditure_rows:
        if row.amount.value is None:
            errors.append(
                ValidationError(
                    code="economic_amount_missing",
                    message=f"expenditure row missing amount: {row.line_text}",
                )
            )
    return errors


def validate_economic_duplicates(
    revenue_rows: Iterable[RevenueRow],
    expenditure_rows: Iterable[EconomicExpenditureRow],
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for label, rows in (
        ("revenue", revenue_rows),
        ("expenditure", expenditure_rows),
    ):
        counts: dict[str, int] = {}
        for row in rows:
            code = row.code.value
            if not code:
                continue
            counts[code] = counts.get(code, 0) + 1
        dupes = sorted(code for code, count in counts.items() if count > 1)
        if dupes:
            errors.append(
                ValidationError(
                    code="economic_duplicate_code",
                    message=f"{label} duplicate codes: {dupes}",
                )
            )
    return errors


def validate_economic_conflicts(
    conflicts: Iterable[EconomicConflict],
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for conflict in conflicts:
        errors.append(
            ValidationError(
                code="economic_conflicting_code",
                message=(
                    f"{conflict.table_type} code {conflict.code} "
                    f"amounts {conflict.first_amount} vs {conflict.second_amount}"
                ),
            )
        )
    return errors


def validate_economic_hierarchy(
    revenue_rows: Iterable[RevenueRow],
    expenditure_rows: Iterable[EconomicExpenditureRow],
) -> list[ValidationError]:
    tolerance = 1.0
    errors: list[ValidationError] = []

    def build_map(rows: Iterable) -> dict[str, float]:
        mapping: dict[str, float] = {}
        for row in rows:
            code = row.code.value
            amount = row.amount.value
            if not code or amount is None:
                continue
            if code not in mapping:
                mapping[code] = float(amount)
        return mapping

    def reconcile(label: str, mapping: dict[str, float]) -> None:
        codes = sorted(mapping.keys(), key=lambda item: (len(item), item))
        for code in codes:
            if len(code) > 2:
                continue
            children = [
                child
                for child in mapping
                if child.startswith(code) and len(child) > len(code)
            ]
            if not children:
                continue
            min_len = min(len(child) for child in children)
            direct_children = [
                child for child in children if len(child) == min_len
            ]
            if len(direct_children) < 2:
                continue
            child_sum = sum(mapping[child] for child in direct_children)
            if abs(mapping[code] - child_sum) > tolerance:
                errors.append(
                    ValidationError(
                        code="economic_reconciliation_failed",
                        message=(
                            f"{label} code {code} expected {mapping[code]} got {round(child_sum, 2)}"
                        ),
                    )
                )

    reconcile("revenue", build_map(revenue_rows))
    reconcile("expenditure", build_map(expenditure_rows))
    return errors
