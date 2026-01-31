from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from engine.schema import EconomicExpenditureRow, ExtractedField, Provenance, RevenueRow


ECON_CODE_RE = re.compile(r"^\s*(\d{1,8})\s+")
NUM_RE = re.compile(r"-?\d{1,3}(?:,\d{3})*(?:\.\d+)?")
HEADER_RE = re.compile(r"^\s*Code\s+Economic\b", re.IGNORECASE)
REVENUE_HEADING_RE = re.compile(r"Revenue by Economic Classification", re.IGNORECASE)
EXPENDITURE_HEADING_RE = re.compile(
    r"Expenditure by Economic Classification", re.IGNORECASE
)

YEAR_BUDGET_RE = re.compile(
    r"(20\d{2})\s+(Approved|Proposed|Revised|Final|Original)\s+Budget",
    re.IGNORECASE,
)
YEAR_STATUS_RE = re.compile(
    r"(20\d{2})\s+(Approved|Proposed|Revised|Final|Original)",
    re.IGNORECASE,
)
YEAR_PERFORMANCE_RE = re.compile(r"(20\d{2})\s+Performance", re.IGNORECASE)
PERIOD_RE = re.compile(r"January\s+to\s+\w+", re.IGNORECASE)
CLIMATE_RE = re.compile(
    r"(20\d{2})\s+Climate\s+Change\s+(Mitigation|Adaptation)\s+Tagging",
    re.IGNORECASE,
)

HEADER_CONTEXT_KEYWORDS = [
    "approved budget",
    "final budget",
    "revised budget",
    "original budget",
    "performance",
    "january to",
    "climate change",
    "budget",
]


@dataclass
class EconomicContext:
    table_type: str
    labels: list[str]


def split_columns(line: str) -> list[str]:
    return [col.strip() for col in re.split(r"\s{2,}", line.rstrip()) if col.strip()]


def infer_labels(header_lines: list[str]) -> list[str]:
    text = " ".join(line.strip() for line in header_lines)
    lower = re.sub(r"\s+", " ", text.lower())

    matches: list[tuple[int, str]] = []
    for match in YEAR_BUDGET_RE.finditer(lower):
        year, status = match.group(1), match.group(2)
        label = f"{year}_{status.lower()}_budget"
        matches.append((match.start(), label))

    for match in YEAR_STATUS_RE.finditer(lower):
        year, status = match.group(1), match.group(2)
        label = f"{year}_{status.lower()}_budget"
        matches.append((match.start(), label))

    for match in YEAR_PERFORMANCE_RE.finditer(lower):
        year = match.group(1)
        label = f"{year}_performance"
        matches.append((match.start(), label))

    for match in PERIOD_RE.finditer(lower):
        label = match.group(0).lower().replace(" ", "_")
        matches.append((match.start(), label))

    for match in CLIMATE_RE.finditer(lower):
        year, kind = match.group(1), match.group(2)
        label = f"{year}_climate_{kind.lower()}"
        matches.append((match.start(), label))

    if not matches:
        return []

    matches.sort(key=lambda item: item[0])
    labels: list[str] = []
    seen = set()
    for _, label in matches:
        if label in seen:
            continue
        labels.append(label)
        seen.add(label)

    revenue_order = [
        "2024_approved_budget",
        "2024_final_budget",
        "2024_performance",
        "2025_approved_budget",
    ]
    if all(item in labels for item in revenue_order):
        ordered = []
        for item in revenue_order:
            ordered.append(item)
        for item in labels:
            if item not in ordered:
                ordered.append(item)
        return ordered
    return labels


def is_header_context_line(line: str) -> bool:
    lower = line.lower()
    if any(keyword in lower for keyword in HEADER_CONTEXT_KEYWORDS):
        return True
    if ECON_CODE_RE.match(line):
        return False
    return False


def select_target_label(labels: list[str], target_year: str) -> Optional[int]:
    year_prefix = f"{target_year}_"
    for idx, label in enumerate(labels):
        if label.startswith(year_prefix) and "approved" in label:
            return idx
    for idx, label in enumerate(labels):
        if label.startswith(year_prefix) and "proposed" in label:
            return idx
    for idx, label in enumerate(labels):
        if label.startswith(year_prefix) and "budget" in label:
            return idx
    return None


def parse_amount(raw: str) -> float | None:
    value = raw.strip()
    if not value:
        return None
    if value in {"-", "–"}:
        return 0.0
    value = value.replace(",", "")
    value = value.replace("(", "-").replace(")", "")
    value = re.sub(r"[^0-9.\-]", "", value)
    if not value or value == "-":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_row(line: str) -> tuple[str, str, list[str]] | None:
    match = re.match(r"^\s*(\d{1,8})\s+(.*)$", line)
    if not match:
        return None
    code = match.group(1)
    rest = match.group(2)
    num_match = NUM_RE.search(rest)
    if not num_match:
        return None
    desc = rest[: num_match.start()].strip()
    amounts = NUM_RE.findall(rest[num_match.start() :])
    return code, desc, amounts


def has_alpha(text: str) -> bool:
    return any(ch.isalpha() for ch in text)


def extract_economic_rows(
    pages: list[str],
    target_year: str,
) -> tuple[list[RevenueRow], list[EconomicExpenditureRow]]:
    revenue_rows: list[RevenueRow] = []
    expenditure_rows: list[EconomicExpenditureRow] = []

    context: Optional[EconomicContext] = None
    current_section: Optional[str] = None
    last_section: Optional[str] = None

    for page_index, page_text in enumerate(pages, start=1):
        lines = page_text.splitlines()
        context = None
        line_index = 0
        while line_index < len(lines):
            line = lines[line_index]

            if REVENUE_HEADING_RE.search(line):
                current_section = "revenue"
                last_section = "revenue"
                context = None
                line_index += 1
                continue

            if EXPENDITURE_HEADING_RE.search(line):
                current_section = "expenditure"
                last_section = "expenditure"
                context = None
                line_index += 1
                continue

            if "Approved Budget -" in line and not HEADER_RE.search(line):
                if not REVENUE_HEADING_RE.search(line) and not EXPENDITURE_HEADING_RE.search(line):
                    current_section = None
                    context = None
                    line_index += 1
                    continue

            if HEADER_RE.search(line):
                if current_section is None and last_section is not None:
                    current_section = last_section
                header_lines = []
                if line_index - 1 >= 0:
                    prev_line = lines[line_index - 1]
                    if is_header_context_line(prev_line):
                        header_lines.append(prev_line)
                header_lines.append(line)
                for offset in (1, 2):
                    if line_index + offset < len(lines):
                        next_line = lines[line_index + offset]
                        if is_header_context_line(next_line):
                            header_lines.append(next_line)
                labels = infer_labels(header_lines)
                if current_section:
                    context = EconomicContext(
                        table_type=current_section,
                        labels=labels,
                    )
                line_index += 1
                continue

            if current_section and context and ECON_CODE_RE.match(line):
                parsed = parse_row(line)
                if not parsed:
                    line_index += 1
                    continue
                code, desc, amount_columns = parsed
                if not desc or not has_alpha(desc):
                    line_index += 1
                    continue
                if not context.labels:
                    line_index += 1
                    continue
                target_index = select_target_label(context.labels, target_year)
                if target_index is None:
                    line_index += 1
                    continue
                if target_index >= len(amount_columns):
                    line_index += 1
                    continue
                amount_value = parse_amount(amount_columns[target_index])
                if amount_value is None:
                    line_index += 1
                    continue
                amount_field = ExtractedField.with_value(
                    amount_value,
                    provenance=[Provenance(page=page_index, line_text=line.strip())],
                )
                code_field = ExtractedField.with_value(code)
                category_field = ExtractedField.with_value(desc)
                subcategory_field = ExtractedField.null("not_extracted")
                if context.table_type == "revenue":
                    revenue_rows.append(
                        RevenueRow(
                            code=code_field,
                            category=category_field,
                            subcategory=subcategory_field,
                            amount=amount_field,
                            classification=ExtractedField.with_value("economic"),
                            page=page_index,
                            line_text=line.strip(),
                        )
                    )
                else:
                    expenditure_rows.append(
                        EconomicExpenditureRow(
                            code=code_field,
                            category=category_field,
                            subcategory=subcategory_field,
                            amount=amount_field,
                            page=page_index,
                            line_text=line.strip(),
                        )
                    )

            line_index += 1

    return revenue_rows, expenditure_rows
