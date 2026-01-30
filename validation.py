from __future__ import annotations

from dataclasses import dataclass


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
