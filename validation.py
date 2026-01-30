from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

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
