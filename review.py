from __future__ import annotations

from collections import Counter

from engine.schema import ExtractionError


def build_review_report(errors: list[ExtractionError]) -> dict[str, object]:
    counts = Counter(error.code for error in errors)
    unique_messages: dict[str, list[str]] = {}
    for error in errors:
        if error.code not in unique_messages:
            unique_messages[error.code] = []
        if error.message not in unique_messages[error.code]:
            unique_messages[error.code].append(error.message)

    return {
        "error_count": len(errors),
        "error_codes": dict(counts),
        "messages": unique_messages,
    }
