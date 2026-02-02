from __future__ import annotations

import re
from typing import Optional

from dataclasses import dataclass

from engine.economic import NUM_RE, infer_labels, parse_amount, select_target_label
from engine.schema import BudgetTotals, ExtractedField, Provenance


SUMMARY_HEADING_RE = re.compile(
    r"Approved Budget Summary|Budget Summary|Proposed\s+\d{4}\s+Budget\s+Summary",
    re.IGNORECASE,
)

SUMMARY_ITEMS = {
    "total_revenue": re.compile(r"\bTotal\s+Revenue\b", re.IGNORECASE),
    "total_expenditure": re.compile(r"\bTotal\s+Expenditure\b", re.IGNORECASE),
    "recurrent_expenditure": re.compile(r"\bRecurrent\s+Expenditure\b", re.IGNORECASE),
    "capital_expenditure": re.compile(r"\bCapital\s+Expenditure\b", re.IGNORECASE),
    "recurrent_revenue": re.compile(r"\bRecurrent\s+Revenue\b", re.IGNORECASE),
}


@dataclass
class SummaryContext:
    recurrent_revenue: ExtractedField | None = None


def extract_budget_summary(
    pages: list[str],
    target_year: str,
) -> tuple[BudgetTotals, SummaryContext]:
    header_labels: list[str] = []
    summary_heading: str | None = None
    summary_heading_page: int | None = None
    summary_page_lines: list[str] = []
    kebbi_style = False

    # scan first page for summary header labels
    for page_index, page_text in enumerate(pages[:50], start=1):
        lines = page_text.splitlines()
        for idx, line in enumerate(lines):
            if SUMMARY_HEADING_RE.search(line):
                header_lines = []
                for offset in (1, 2, 3, 4):
                    if idx + offset < len(lines):
                        header_lines.append(lines[idx + offset])
                labels = infer_labels(header_lines)
                if not labels:
                    labels = _infer_summary_labels(header_lines)
                if len(labels) > len(header_labels):
                    header_labels = labels
                    summary_heading = line.strip()
                    summary_heading_page = page_index
                    summary_page_lines = lines
                    kebbi_style = "Budget" in " ".join(header_lines)

    if not summary_page_lines:
        for page_index, page_text in enumerate(pages[:50], start=1):
            lines = page_text.splitlines()
            for idx, line in enumerate(lines):
                if "Approved Budget Summary" in line or "Budget Summary" in line:
                    summary_heading = line.strip()
                    summary_heading_page = page_index
                    summary_page_lines = lines
                    header_lines = []
                    for offset in (1, 2, 3, 4, 5):
                        if idx + offset < len(lines):
                            header_lines.append(lines[idx + offset])
                    header_labels = _infer_summary_labels(header_lines)
                    kebbi_style = "Budget" in " ".join(header_lines)
                    break

    if not summary_page_lines:
        for page_index, page_text in enumerate(pages[:5], start=1):
            lines = page_text.splitlines()
            for idx, line in enumerate(lines):
                if "Approved Budget Summary" in line or "Budget Summary" in line:
                    summary_heading = line.strip()
                    summary_heading_page = page_index
                    summary_page_lines = lines
                    for offset in (1, 2, 3, 4, 5):
                        if idx + offset < len(lines):
                            header_labels.extend(
                                _infer_summary_labels([lines[idx + offset]])
                            )
                    break

    totals = {
        "total_budget": ExtractedField.null("not_extracted"),
        "capital_expenditure_total": ExtractedField.null("not_extracted"),
        "recurrent_expenditure_total": ExtractedField.null("not_extracted"),
        "revenue_total": ExtractedField.null("not_extracted"),
        "financing_total": ExtractedField.null("not_extracted"),
        "budget_summary_text": ExtractedField.null("not_extracted"),
    }
    recurrent_revenue_value: ExtractedField | None = None

    if not header_labels:
        return BudgetTotals(**totals), SummaryContext()

    target_index = select_target_label(header_labels, target_year)
    if target_index is None and kebbi_style:
        # fallback for kebbi-style header order
        if len(header_labels) >= 4:
            target_index = 3
    if target_index is None:
        return BudgetTotals(**totals), SummaryContext()

    if not summary_page_lines:
        return BudgetTotals(**totals), SummaryContext()

    page_index = summary_heading_page or 1
    context = SummaryContext()
    for line in summary_page_lines:
        for key, pattern in SUMMARY_ITEMS.items():
            if not pattern.search(line):
                continue
            match = NUM_RE.search(line)
            if not match:
                continue
            label_text = line[: match.start()].strip()
            amount_columns = NUM_RE.findall(line[match.start() :])
            if label_text.startswith("23 -") or label_text.startswith("11 -"):
                if amount_columns and amount_columns[0].isdigit() and len(amount_columns) > 1:
                    amount_columns = amount_columns[1:]
            if len(amount_columns) == 4:
                if target_year == "2025":
                    target_idx = 3
                else:
                    target_idx = 1
            else:
                target_idx = target_index
            if re.match(r"^\s*\d+\s*-", line):
                amount_columns = amount_columns[1:]
            if target_idx is None or target_idx >= len(amount_columns):
                continue
            amount_value = parse_amount(amount_columns[target_idx])
            if amount_value is None:
                continue
            totals_map = {
                "total_revenue": "revenue_total",
                "total_expenditure": "total_budget",
                "recurrent_expenditure": "recurrent_expenditure_total",
                "capital_expenditure": "capital_expenditure_total",
                "recurrent_revenue": "recurrent_revenue",
            }
            field_key = totals_map[key]
            field_value = ExtractedField.with_value(
                amount_value,
                provenance=[Provenance(page=page_index, line_text=line.strip())],
            )
            if field_key == "recurrent_revenue":
                recurrent_revenue_value = field_value
            else:
                totals[field_key] = field_value
            if key == "capital_expenditure":
                if len(amount_columns) == 4 and target_year == "2025":
                    totals["capital_expenditure_total"] = ExtractedField.with_value(
                        parse_amount(amount_columns[3]) or amount_value,
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

    if totals["revenue_total"].value is None and recurrent_revenue_value is not None:
        totals["revenue_total"] = recurrent_revenue_value
    context.recurrent_revenue = recurrent_revenue_value

    return BudgetTotals(**totals), context


def _infer_summary_labels(header_lines: list[str]) -> list[str]:
    lower = " ".join(line.strip() for line in header_lines).lower()
    matches: list[tuple[int, str]] = []
    patterns = [
        (r"(20\d{2})\s+original\s+budget", "original_budget"),
        (r"(20\d{2})\s+revised\s+budget", "revised_budget"),
        (r"(20\d{2})\s+performance", "performance"),
        (r"(20\d{2})\s+approved\b", "approved_budget"),
    ]
    for pattern, label in patterns:
        for match in re.finditer(pattern, lower):
            year = match.group(1)
            matches.append((match.start(), f"{year}_{label}"))
    matches.sort(key=lambda item: item[0])
    labels: list[str] = []
    seen = set()
    for _, label in matches:
        if label in seen:
            continue
        labels.append(label)
        seen.add(label)
    return labels
