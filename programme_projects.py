from __future__ import annotations

import re
from typing import Optional

from engine.economic import NUM_RE, parse_amount, select_target_label, split_columns
from engine.schema import AmountItem, ExtractedField, ProgrammeRow, Provenance


PROGRAM_HEADER_RE = re.compile(
    r"Programme Code and Programme Description", re.IGNORECASE
)
PROJECT_HEADER_RE = re.compile(r"Project Description", re.IGNORECASE)

PROGRAM_CODE_RE = re.compile(r"^\s*(\d{11,14})\s*-\s*(.+)$")
ECON_COL_RE = re.compile(r"^\s*(\d{8})\s*-\s*(.+)$")
FUNC_COL_RE = re.compile(r"^\s*(\d{5})\s*-\s*(.+)$")
FUND_COL_RE = re.compile(r"^\s*(\d{2,8})\s*-\s*(.+)$")
LOC_COL_RE = re.compile(r"^\s*(\d{8})\s*-\s*(.+)$")

HEADER_CONTEXT_KEYWORDS = [
    "full year actuals",
    "revised budget",
    "draft budget",
    "approved budget",
    "adjustments",
    "out-year estimate",
    "performance",
    "january to",
]

SECTOR_RE = re.compile(r"\bsector\b", re.IGNORECASE)
OBJECTIVE_RE = re.compile(r"\bobjective\b", re.IGNORECASE)
OBJECTIVE_LINE_RE = re.compile(r"^[A-Za-z].{0,80}\s-\s[A-Za-z].*$")

FUND_HEADER_RE = re.compile(r"Fund Code|Funding Source", re.IGNORECASE)


def is_header_context_line(line: str) -> bool:
    lower = line.lower()
    return any(keyword in lower for keyword in HEADER_CONTEXT_KEYWORDS)


def infer_labels(header_lines: list[str]) -> list[str]:
    text = " ".join(line.strip() for line in header_lines)
    lower = re.sub(r"\s+", " ", text.lower())

    patterns = [
        (r"(20\d{2})\s+full year actuals", "full_year_actuals"),
        (r"(20\d{2})\s+revised budget", "revised_budget"),
        (r"(20\d{2})\s+approved budget", "approved_budget"),
        (r"(20\d{2})\s+adjustments", "adjustments"),
        (r"(20\d{2})\s+out-year estimate", "out_year_estimate"),
    ]

    matches: list[tuple[int, str]] = []
    for pattern, label in patterns:
        for match in re.finditer(pattern, lower):
            year = match.group(1)
            matches.append((match.start(), f"{year}_{label}"))

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
    return labels


def parse_code_desc(value: str, pattern: re.Pattern[str]) -> tuple[str, str] | None:
    match = pattern.match(value)
    if not match:
        return None
    return match.group(1), match.group(2).strip()


def parse_program_line(line: str) -> tuple[str, str] | None:
    match = PROGRAM_CODE_RE.match(line)
    if not match:
        return None
    return match.group(1), match.group(2).strip()


def extract_programme_projects(
    pages: list[str],
    target_year: str,
) -> list[ProgrammeRow]:
    rows: list[ProgrammeRow] = []

    current_program_code: Optional[str] = None
    current_program_desc = ""
    program_continuation: list[str] = []
    project_buffer: list[str] = []
    labels: list[str] = []
    target_index: Optional[int] = None
    has_fund_column = False
    current_sector: Optional[str] = None
    current_objective: Optional[str] = None

    for page_index, page_text in enumerate(pages, start=1):
        lines = page_text.splitlines()
        line_index = 0
        while line_index < len(lines):
            line = lines[line_index]

            if PROGRAM_HEADER_RE.search(line) and PROJECT_HEADER_RE.search(line):
                header_lines = []
                if line_index - 1 >= 0 and is_header_context_line(lines[line_index - 1]):
                    header_lines.append(lines[line_index - 1])
                header_lines.append(line)
                for offset in (1, 2):
                    if line_index + offset < len(lines) and is_header_context_line(
                        lines[line_index + offset]
                    ):
                        header_lines.append(lines[line_index + offset])
                labels = infer_labels(header_lines)
                target_index = select_target_label(labels, target_year)
                header_columns = split_columns(line)
                has_fund_column = any(FUND_HEADER_RE.search(col) for col in header_columns)
                current_program_code = None
                current_program_desc = ""
                program_continuation = []
                project_buffer = []
                current_sector = None
                current_objective = None
                line_index += 1
                continue

            if not labels or target_index is None:
                line_index += 1
                continue

            if not line.strip() or line.strip().lower() == "total":
                line_index += 1
                continue

            if not PROGRAM_CODE_RE.match(line) and not ECON_COL_RE.match(line):
                if SECTOR_RE.search(line) and not re.search(r"\d", line):
                    if _is_short_label(line):
                        current_sector = _trim_label(line)
                        line_index += 1
                        continue
                if OBJECTIVE_RE.search(line) and not re.search(r"\d", line):
                    if _is_short_label(line):
                        current_objective = _trim_label(line)
                        line_index += 1
                        continue
                if OBJECTIVE_LINE_RE.match(line) and not re.search(r"\d", line):
                    if _is_short_label(line):
                        current_objective = _trim_label(line)
                        line_index += 1
                        continue

            program_line = parse_program_line(line)
            columns = split_columns(line)
            econ_index = None
            for idx, col in enumerate(columns):
                if ECON_COL_RE.match(col):
                    econ_index = idx
                    break

            if program_line:
                if columns and columns[0] != line:
                    parsed = parse_program_line(columns[0])
                    if parsed:
                        current_program_code, current_program_desc = parsed
                    else:
                        current_program_code, current_program_desc = program_line
                else:
                    current_program_code, current_program_desc = program_line
                program_continuation = []
                project_buffer = []

                if len(columns) > 1:
                    # columns[0] includes program code + desc
                    if econ_index is None:
                        project_buffer.append(columns[1])
                    else:
                        project_buffer.extend(columns[1:econ_index])

                if econ_index is None:
                    line_index += 1
                    continue
            elif econ_index is None:
                if current_program_code:
                    if len(columns) >= 2:
                        program_continuation.append(columns[0])
                        project_buffer.append(columns[1])
                    elif columns:
                        if not project_buffer:
                            program_continuation.append(columns[0])
                        else:
                            project_buffer.append(columns[0])
                    if OBJECTIVE_RE.search(columns[0]) and not re.search(r"\d", columns[0]):
                        if _is_short_label(columns[0]):
                            current_objective = _trim_label(columns[0])
                line_index += 1
                continue

            if econ_index is None:
                line_index += 1
                continue

            if not current_program_code:
                line_index += 1
                continue

            econ_col = columns[econ_index]
            func_col = columns[econ_index + 1] if len(columns) > econ_index + 1 else ""
            fund_col = ""
            loc_col = ""
            if has_fund_column:
                fund_col = columns[econ_index + 2] if len(columns) > econ_index + 2 else ""
                loc_col = columns[econ_index + 3] if len(columns) > econ_index + 3 else ""
                amount_cols = columns[econ_index + 4 :]
            else:
                loc_col = columns[econ_index + 2] if len(columns) > econ_index + 2 else ""
                amount_cols = columns[econ_index + 3 :]

            econ_parsed = parse_code_desc(econ_col, ECON_COL_RE)
            func_parsed = parse_code_desc(func_col, FUNC_COL_RE)
            loc_parsed = parse_code_desc(loc_col, LOC_COL_RE)
            fund_parsed = None
            if has_fund_column:
                fund_parsed = parse_code_desc(fund_col, FUND_COL_RE)

            if not econ_parsed or not func_parsed or not loc_parsed:
                line_index += 1
                continue
            if has_fund_column and not fund_parsed:
                line_index += 1
                continue

            labels_for_row = labels
            amount_value = None
            use_target = target_index is not None
            if len(amount_cols) != len(labels):
                labels_for_row = [f"amount_{i + 1}" for i in range(len(amount_cols))]
                use_target = False

            amounts: list[AmountItem] = []
            valid = True
            for idx, label in enumerate(labels_for_row):
                raw_value = amount_cols[idx] if idx < len(amount_cols) else ""
                parsed_value = parse_amount(raw_value)
                if parsed_value is None:
                    valid = False
                    break
                amount_field = ExtractedField.with_value(
                    parsed_value,
                    provenance=[Provenance(page=page_index, line_text=line.strip())],
                )
                amounts.append(AmountItem(label=label, amount=amount_field))
                if use_target and target_index is not None and idx == target_index:
                    amount_value = parsed_value
            if not valid:
                line_index += 1
                continue

            program_desc = " ".join([current_program_desc] + program_continuation)
            program_desc = re.sub(r"\s+", " ", program_desc).strip()
            project_desc = " ".join(project_buffer).strip()

            if not program_desc or not project_desc:
                line_index += 1
                continue

            econ_code, econ_desc = econ_parsed
            func_code, func_desc = func_parsed
            loc_code, loc_desc = loc_parsed

            rows.append(
                ProgrammeRow(
                    sector=(
                        ExtractedField.with_value(
                            current_sector,
                            provenance=[
                                Provenance(page=page_index, line_text=line.strip())
                            ],
                        )
                        if current_sector
                        else ExtractedField.null("not_extracted")
                    ),
                    objective=(
                        ExtractedField.with_value(
                            current_objective,
                            provenance=[
                                Provenance(page=page_index, line_text=line.strip())
                            ],
                        )
                        if current_objective
                        else ExtractedField.null("not_extracted")
                    ),
                    programme_code=ExtractedField.with_value(current_program_code),
                    programme=ExtractedField.with_value(program_desc),
                    project_name=ExtractedField.with_value(project_desc),
                    economic_code=ExtractedField.with_value(econ_code),
                    economic_description=ExtractedField.with_value(econ_desc),
                    function_code=ExtractedField.with_value(func_code),
                    function_description=ExtractedField.with_value(func_desc),
                    location_code=ExtractedField.with_value(loc_code),
                    location_description=ExtractedField.with_value(loc_desc),
                    amounts=amounts,
                    amount_labels=labels_for_row,
                    amount=(
                        ExtractedField.with_value(
                            amount_value,
                            provenance=[
                                Provenance(page=page_index, line_text=line.strip())
                            ],
                        )
                        if amount_value is not None
                        else ExtractedField.null("not_extracted")
                    ),
                    funding_source=(
                        ExtractedField.with_value(
                            f"{fund_parsed[0]} - {fund_parsed[1]}",
                            provenance=[
                                Provenance(page=page_index, line_text=line.strip())
                            ],
                        )
                        if fund_parsed
                        else ExtractedField.null("not_extracted")
                    ),
                    page=page_index,
                    line_text=line.strip(),
                )
            )

            current_program_code = None
            current_program_desc = ""
            program_continuation = []
            project_buffer = []

            line_index += 1

    return rows


def _is_short_label(line: str) -> bool:
    cleaned = re.sub(r"\s+", " ", line.strip())
    if not cleaned:
        return False
    if any(token in cleaned.lower() for token in ["programme", "project"]):
        return False
    if len(cleaned) > 60:
        return False
    words = cleaned.split(" ")
    return 1 <= len(words) <= 6


def _trim_label(line: str) -> str:
    return re.split(r"\s{2,}", line.strip())[0]
