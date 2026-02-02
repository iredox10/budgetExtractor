from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from engine.admin_units import ParentRow
from engine.economic import EconomicConflict
from engine.schema import AdministrativeUnit, BudgetTotals, EconomicExpenditureRow, RevenueRow


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


def validate_programme_rows(rows: Iterable) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for row in rows:
        for item in getattr(row, "amounts", []):
            if item.amount.value is None:
                errors.append(
                    ValidationError(
                        code="programme_amount_missing",
                        message=f"programme row missing amount: {row.line_text}",
                    )
                )
                break
    return errors


def validate_budget_components(budget_totals: BudgetTotals) -> list[ValidationError]:
    errors: list[ValidationError] = []
    total = budget_totals.total_budget.value
    capital = budget_totals.capital_expenditure_total.value
    recurrent = budget_totals.recurrent_expenditure_total.value
    if total is None or capital is None or recurrent is None:
        return errors
    if abs(total - (capital + recurrent)) > 1.0:
        errors.append(
            ValidationError(
                code="budget_totals_mismatch",
                message=(
                    f"total budget {total} != capital {capital} + recurrent {recurrent}"
                ),
            )
        )
    return errors


def validate_global_reconciliation(
    budget_totals: BudgetTotals,
    revenue_rows: Iterable[RevenueRow],
    expenditure_rows: Iterable[EconomicExpenditureRow],
    mda_rows: Iterable,
    programme_rows: Iterable,
    revenue_reference: str | None = None,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    tolerance = 1.0

    def leaf_sum(rows: Iterable) -> float | None:
        mapping: dict[str, float] = {}
        for row in rows:
            code = row.code.value
            amount = row.amount.value
            if not code or amount is None:
                continue
            if code not in mapping:
                mapping[code] = float(amount)

        if not mapping:
            return None

        leaf_codes = []
        for code in mapping:
            if not any(
                other.startswith(code) and len(other) > len(code) for other in mapping
            ):
                leaf_codes.append(code)
        if not leaf_codes:
            return None
        return sum(mapping[code] for code in leaf_codes)

    total_budget = budget_totals.total_budget.value
    if total_budget is not None:
        exp_sum = leaf_sum(expenditure_rows)
        if exp_sum is not None and abs(total_budget - exp_sum) > tolerance:
            errors.append(
                ValidationError(
                    code="global_expenditure_mismatch",
                    message=(
                        f"total budget {total_budget} != economic expenditure {round(exp_sum, 2)}"
                    ),
                )
            )

        mda_totals = [
            row.total_amount.value for row in mda_rows if row.total_amount.value is not None
        ]
        if mda_totals and len(mda_totals) == len(list(mda_rows)):
            mda_sum = sum(float(value) for value in mda_totals)
            if abs(total_budget - mda_sum) > tolerance:
                errors.append(
                    ValidationError(
                        code="global_mda_mismatch",
                        message=(
                            f"total budget {total_budget} != mda total {round(mda_sum, 2)}"
                        ),
                    )
                )

        programme_values = [
            row.amount.value for row in programme_rows if row.amount.value is not None
        ]
        if programme_values and len(programme_values) == len(list(programme_rows)):
            programme_sum = sum(float(value) for value in programme_values)
            if abs(total_budget - programme_sum) > tolerance:
                errors.append(
                    ValidationError(
                        code="global_programme_mismatch",
                        message=(
                            f"total budget {total_budget} != programme total {round(programme_sum, 2)}"
                        ),
                    )
                )

    revenue_total = budget_totals.revenue_total.value
    if revenue_reference == "recurrent_revenue":
        revenue_total = budget_totals.revenue_total.value
    if revenue_total is not None:
        rev_sum = leaf_sum(revenue_rows)
        if rev_sum is not None and abs(revenue_total - rev_sum) > tolerance:
            errors.append(
                ValidationError(
                    code="global_revenue_mismatch",
                    message=(
                        f"total revenue {revenue_total} != economic revenue {round(rev_sum, 2)}"
                    ),
                )
            )

    return errors


def validate_metadata_consistency(metadata, pdf_path: Path) -> list[ValidationError]:
    errors: list[ValidationError] = []
    file_year = None
    match = re.search(r"(20\d{2})", pdf_path.name)
    if match:
        file_year = match.group(1)
    if file_year and metadata.budget_year.value and file_year != metadata.budget_year.value:
        errors.append(
            ValidationError(
                code="metadata_year_mismatch",
                message=(
                    f"filename year {file_year} != extracted year {metadata.budget_year.value}"
                ),
            )
        )

    if "_" in pdf_path.stem:
        file_state = pdf_path.stem.split("_", 1)[0].strip().lower()
        if metadata.state_name.value and file_state:
            extracted_state = metadata.state_name.value.lower()
            if file_state not in extracted_state and extracted_state not in file_state:
                errors.append(
                    ValidationError(
                        code="metadata_state_mismatch",
                        message=(
                            f"filename state {file_state} != extracted state {extracted_state}"
                        ),
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
