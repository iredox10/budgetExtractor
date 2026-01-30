from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from engine.schema import AmountItem, AdministrativeUnit, ExtractedField, Provenance


ADMIN_CODE_RE = re.compile(r"^\s*(\d{6,})")
PARENT_CODE_RE = re.compile(r"^\d{6,}0{4,}$")


HEADER_KEYWORDS = [
    "administrative unit",
    "admin description",
    "adminstrative unit",
]

HEADER_CONTEXT_KEYWORDS = [
    "personnel",
    "overhead",
    "total recurrent",
    "capital",
    "total expenditure",
    "recurrent",
    "development",
    "other",
    "federation account",
    "independent revenue",
    "aids and grants",
    "fund receipts",
    "total revenue",
    "igr",
]


@dataclass
class HeaderContext:
    labels: list[str]
    table_type: str


def is_header_line(line: str) -> bool:
    lower = line.lower()
    if "code" not in lower:
        return False
    return any(keyword in lower for keyword in HEADER_KEYWORDS)


def is_header_context_line(line: str) -> bool:
    if ADMIN_CODE_RE.match(line):
        return False
    lower = line.lower()
    return any(keyword in lower for keyword in HEADER_CONTEXT_KEYWORDS)


def infer_labels(header_lines: list[str]) -> HeaderContext:
    text = " ".join(line.strip() for line in header_lines)
    lower = re.sub(r"\s+", " ", text.lower())
    signature = hashlib.sha1(lower.encode("utf-8")).hexdigest()[:8]

    if (
        "personnel" in lower
        and "overhead" in lower
        and "total recurrent" in lower
        and "capital" in lower
        and "total expenditure" in lower
    ):
        return HeaderContext(
            labels=[
                "personnel",
                "overhead",
                "total_recurrent",
                "capital",
                "total_expenditure",
            ],
            table_type="expenditure_mda",
        )

    if (
        "personnel expenditure" in lower
        and "capital expenditure" in lower
        and "total expenditure" in lower
    ):
        return HeaderContext(
            labels=[
                "personnel",
                "overhead",
                "total_recurrent",
                "capital",
                "total_expenditure",
            ],
            table_type="expenditure_mda",
        )

    if "recurrent" in lower and "development" in lower and "other" in lower:
        return HeaderContext(
            labels=["recurrent", "development", "other"],
            table_type="expenditure_admin",
        )

    if (
        "federation account" in lower
        and "independent revenue" in lower
        and "aids and grants" in lower
        and "fund receipts" in lower
        and "total revenue" in lower
    ):
        return HeaderContext(
            labels=[
                "federation_account_revenues",
                "independent_revenue",
                "aids_and_grants",
                "capital_development_fund_receipts",
                "total_revenue",
            ],
            table_type="revenue_mda",
        )

    ordered = []
    label_patterns = [
        ("total_expenditure", r"total\s+expenditure"),
        ("total_recurrent", r"total\s+recurrent"),
        ("independent_revenue", r"independent\s+revenue"),
        ("federation_account_revenues", r"federation\s+account"),
        ("capital_development_fund_receipts", r"fund\s+receipts"),
        ("aids_and_grants", r"aids\s+and\s+grants"),
        ("personnel", r"personnel"),
        ("overhead", r"overhead"),
        ("capital", r"capital"),
        ("recurrent", r"recurrent"),
        ("development", r"development"),
        ("other", r"other"),
        ("total_revenue", r"total\s+revenue"),
    ]
    for label, pattern in label_patterns:
        for match in re.finditer(pattern, lower):
            ordered.append((match.start(), label))

    if ordered:
        ordered.sort(key=lambda item: item[0])
        labels = []
        seen = set()
        for _, label in ordered:
            if label in seen:
                continue
            labels.append(label)
            seen.add(label)
        return HeaderContext(labels=labels, table_type=f"unknown_{signature}")

    return HeaderContext(labels=[], table_type=f"unknown_{signature}")


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


def split_columns(line: str) -> list[str]:
    return [col.strip() for col in re.split(r"\s{2,}", line.rstrip()) if col.strip()]


def parse_row(line: str) -> tuple[str, str, list[str]] | None:
    columns = split_columns(line)
    if not columns:
        return None
    code_match = ADMIN_CODE_RE.match(columns[0])
    if not code_match:
        return None
    code = code_match.group(1)
    name = columns[0][len(code) :].strip()
    amount_columns = columns[1:]
    if not name and len(columns) > 1:
        name = columns[1].strip()
        amount_columns = columns[2:]
    return code, name, amount_columns


def is_parent_code(code: str) -> bool:
    return bool(PARENT_CODE_RE.match(code))


def find_parent_code(unit_code: str, parent_codes: list[str]) -> str | None:
    candidates = []
    for parent in parent_codes:
        prefix = parent.rstrip("0")
        if prefix and unit_code.startswith(prefix):
            candidates.append((len(prefix), parent))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0], reverse=True)[0][1]


def extract_admin_units(pages: list[str]) -> tuple[list[AdministrativeUnit], dict[str, str]]:
    admin_units: list[AdministrativeUnit] = []
    parents: dict[str, str] = {}
    seen_units: set[tuple[str, str]] = set()
    allowed_table_types = {"expenditure_mda", "revenue_mda", "expenditure_admin"}

    for page_index, page_text in enumerate(pages, start=1):
        lines = page_text.splitlines()
        header_context: HeaderContext | None = None
        header_buffer: list[str] = []

        line_index = 0
        while line_index < len(lines):
            line = lines[line_index]
            if not line.strip():
                line_index += 1
                continue

            if line.strip().isdigit():
                line_index += 1
                continue
            if is_header_line(line):
                header_buffer = []
                if line_index - 1 >= 0:
                    prev_line = lines[line_index - 1]
                    if is_header_context_line(prev_line):
                        header_buffer.append(prev_line)
                header_buffer.append(line)
                for offset in (1, 2):
                    if line_index + offset < len(lines):
                        next_line = lines[line_index + offset]
                        if is_header_context_line(next_line):
                            header_buffer.append(next_line)
                header_context = infer_labels(header_buffer)
                if header_context.table_type.startswith("unknown"):
                    header_context = None
                elif header_context.table_type not in allowed_table_types:
                    header_context = None
                line_index += 1
                continue

            if ADMIN_CODE_RE.match(line) and header_context is None:
                line_index += 1
                continue

            if header_context and ADMIN_CODE_RE.match(line):
                parsed = parse_row(line)
                if not parsed:
                    line_index += 1
                    continue
                code, name, amount_columns = parsed
                if not name:
                    line_index += 1
                    continue

                if is_parent_code(code):
                    parents[code] = name
                    line_index += 1
                    continue

                amounts: list[AmountItem] = []
                labels = header_context.labels
                if not labels:
                    labels = [f"amount_{i + 1}" for i in range(len(amount_columns))]

                max_len = max(len(labels), len(amount_columns))
                for idx in range(max_len):
                    label = labels[idx] if idx < len(labels) else f"amount_{idx + 1}"
                    raw_value = amount_columns[idx] if idx < len(amount_columns) else ""
                    parsed_value = parse_amount(raw_value)
                    if parsed_value is None:
                        amount_field = ExtractedField.null("missing_amount")
                    else:
                        amount_field = ExtractedField.with_value(
                            parsed_value,
                            provenance=[
                                Provenance(page=page_index, line_text=line.strip())
                            ],
                        )
                    amounts.append(AmountItem(label=label, amount=amount_field))

                if not any(item.amount.value is not None for item in amounts):
                    line_index += 1
                    continue

                if any(item.amount.value is None for item in amounts):
                    line_index += 1
                    continue

                parent_code = find_parent_code(code, list(parents.keys()))
                if parent_code:
                    parent_name = parents.get(parent_code, "")
                    parent_code_field = ExtractedField.with_value(parent_code)
                    parent_name_field = ExtractedField.with_value(parent_name)
                else:
                    parent_code_field = ExtractedField.null("parent_not_found")
                    parent_name_field = ExtractedField.null("parent_not_found")

                unit = AdministrativeUnit(
                    parent_code=parent_code_field,
                    parent_name=parent_name_field,
                    unit_code=ExtractedField.with_value(code),
                    unit_name=ExtractedField.with_value(name),
                    amounts=amounts,
                    page=page_index,
                    line_text=line.strip(),
                    table_type=header_context.table_type,
                )
                unit_key = (unit.table_type, code)
                if unit_key not in seen_units:
                    admin_units.append(unit)
                    seen_units.add(unit_key)

            line_index += 1

    return admin_units, parents
