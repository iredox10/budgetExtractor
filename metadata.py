from __future__ import annotations

import re
from pathlib import Path

from engine.schema import ExtractedField, Provenance


TITLE_PATTERNS = [
    re.compile(r"Approved\s+Budget", re.IGNORECASE),
    re.compile(r"Budget\s+Document", re.IGNORECASE),
    re.compile(r"Appropriation", re.IGNORECASE),
]

TITLE_EXCLUDE = re.compile(
    r"Revenue by|Expenditure by|Economic Classification|Programme|Programmes|"
    r"Projects|Administrative|Full Year Actuals",
    re.IGNORECASE,
)

STATE_RE = re.compile(r"([A-Z][A-Z &.\-]+)\s+STATE", re.IGNORECASE)
YEAR_RE = re.compile(r"(20\d{2})")
STATE_CODE_RE = re.compile(r"State\s+Code\s*[:\-]\s*([A-Z]{2,4})", re.IGNORECASE)


def extract_metadata(pdf_path: Path, pages: list[str]) -> dict[str, ExtractedField[str]]:
    state_name = ExtractedField.null("not_extracted")
    state_code = ExtractedField.null("not_extracted")
    budget_year = ExtractedField.null("not_extracted")
    document_title = ExtractedField.null("not_extracted")
    currency = ExtractedField.null("not_extracted")

    title_line = ""
    title_page = None

    for page_index, page_text in enumerate(pages[:2], start=1):
        for line in page_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if TITLE_EXCLUDE.search(stripped):
                continue
            if any(pattern.search(stripped) for pattern in TITLE_PATTERNS):
                title_line = stripped
                title_page = page_index
                break
        if title_line:
            break

    if title_line and title_page is not None:
        document_title = ExtractedField.with_value(
            title_line,
            provenance=[Provenance(page=title_page, line_text=title_line)],
        )
        state_match = STATE_RE.search(title_line.upper())
        if state_match:
            state_value = state_match.group(1).title()
            state_name = ExtractedField.with_value(
                state_value,
                provenance=[Provenance(page=title_page, line_text=title_line)],
            )
        year_match = YEAR_RE.search(title_line)
        if year_match:
            budget_year = ExtractedField.with_value(
                year_match.group(1),
                provenance=[Provenance(page=title_page, line_text=title_line)],
            )

    for page_index, page_text in enumerate(pages[:3], start=1):
        for line in page_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if "NGN" in stripped or "NAIRA" in stripped.upper() or "\u20A6" in stripped:
                currency = ExtractedField.with_value(
                    "NGN",
                    provenance=[Provenance(page=page_index, line_text=stripped)],
                )
                break
        if currency.value is not None:
            break

    for page_index, page_text in enumerate(pages[:2], start=1):
        for line in page_text.splitlines():
            match = STATE_CODE_RE.search(line)
            if match:
                state_code = ExtractedField.with_value(
                    match.group(1),
                    provenance=[Provenance(page=page_index, line_text=line.strip())],
                )
                break
        if state_code.value is not None:
            break

    if budget_year.value is None:
        year_match = YEAR_RE.search(pdf_path.name)
        if year_match:
            budget_year = ExtractedField(
                value=year_match.group(1),
                reason="from_filename",
                provenance=[],
            )

    if state_name.value is None:
        if "_" in pdf_path.stem:
            state_prefix = pdf_path.stem.split("_", 1)[0].strip()
            if state_prefix:
                state_name = ExtractedField(
                    value=state_prefix,
                    reason="from_filename",
                    provenance=[],
                )

    return {
        "state_name": state_name,
        "state_code": state_code,
        "budget_year": budget_year,
        "document_title": document_title,
        "currency": currency,
    }
