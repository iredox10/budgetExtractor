from __future__ import annotations

import re
from typing import Optional

from engine.economic import NUM_RE, infer_labels, parse_amount, select_target_label
from engine.schema import BudgetTotals, ExtractedField, Provenance


SUMMARY_HEADING_RE = re.compile(r"Approved Budget Summary|Budget Summary", re.IGNORECASE)

SUMMARY_ITEMS = {
    "total_revenue": re.compile(r"\bTotal\s+Revenue\b", re.IGNORECASE),
    "total_expenditure": re.compile(r"\bTotal\s+Expenditure\b", re.IGNORECASE),
    "recurrent_expenditure": re.compile(r"\bRecurrent\s+Expenditure\b", re.IGNORECASE),
    "capital_expenditure": re.compile(r"\bCapital\s+Expenditure\b", re.IGNORECASE),
}


def extract_budget_summary(
    pages: list[str],
    target_year: str,
) -> BudgetTotals:
    header_labels: list[str] = []
    summary_heading: str | None = None
    summary_heading_page: int | None = None

    # scan first page for summary header labels
    if pages:
        lines = pages[0].splitlines()
        for idx, line in enumerate(lines):
            if SUMMARY_HEADING_RE.search(line):
                header_lines = []
                if idx + 1 < len(lines):
                    header_lines.append(lines[idx + 1])
                if idx + 2 < len(lines):
                    header_lines.append(lines[idx + 2])
                labels = infer_labels(header_lines)
                if len(labels) > len(header_labels):
                    header_labels = labels
                    summary_heading = line.strip()
                    summary_heading_page = 1

    totals = {
        "total_budget": ExtractedField.null("not_extracted"),
        "capital_expenditure_total": ExtractedField.null("not_extracted"),
        "recurrent_expenditure_total": ExtractedField.null("not_extracted"),
        "revenue_total": ExtractedField.null("not_extracted"),
        "financing_total": ExtractedField.null("not_extracted"),
        "budget_summary_text": ExtractedField.null("not_extracted"),
    }

    if not header_labels:
        return BudgetTotals(**totals)

    target_index = select_target_label(header_labels, target_year)
    if target_index is None:
        return BudgetTotals(**totals)

    if not pages:
        return BudgetTotals(**totals)

    page_index = 1
    lines = pages[0].splitlines()
    for line in lines:
        for key, pattern in SUMMARY_ITEMS.items():
            if not pattern.search(line):
                continue
            match = NUM_RE.search(line)
            if not match:
                continue
            label_text = line[: match.start()].strip()
            amount_columns = NUM_RE.findall(line[match.start() :])
            if re.match(r"^\s*\d+\s*-", line):
                amount_columns = amount_columns[1:]
            if target_index >= len(amount_columns):
                continue
            amount_value = parse_amount(amount_columns[target_index])
            if amount_value is None:
                continue
            totals_map = {
                "total_revenue": "revenue_total",
                "total_expenditure": "total_budget",
                "recurrent_expenditure": "recurrent_expenditure_total",
                "capital_expenditure": "capital_expenditure_total",
            }
            field_key = totals_map[key]
            totals[field_key] = ExtractedField.with_value(
                amount_value,
                provenance=[Provenance(page=page_index, line_text=line.strip())],
            )
            if totals["budget_summary_text"].value is None and summary_heading:
                totals["budget_summary_text"] = ExtractedField.with_value(
                    summary_heading,
                    provenance=[
                        Provenance(
                            page=summary_heading_page or 1,
                            line_text=summary_heading,
                        )
                    ],
                )

    return BudgetTotals(**totals)
