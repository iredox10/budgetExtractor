from __future__ import annotations

import re
from typing import Optional

from engine.economic import NUM_RE, parse_amount, select_target_label, split_columns
from engine.schema import ExtractedField, Provenance


HEADER_RE = re.compile(r"Functional Classification", re.IGNORECASE)
CODE_RE = re.compile(r"^(\d{3,6})\s+(.+)$")
CODE_ONLY_RE = re.compile(r"^(\d{3,6})\s*$")


def extract_functional_classification(
    pages: list[str],
    target_year: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    labels: list[str] = []
    target_index: Optional[int] = None
    in_table = False

    for page_index, page_text in enumerate(pages, start=1):
        lines = page_text.splitlines()
        line_index = 0
        if not any(HEADER_RE.search(line) for line in lines):
            continue

        while line_index < len(lines):
            line = lines[line_index]
            if HEADER_RE.search(line):
                header_lines = []
                if line_index + 1 < len(lines):
                    header_lines.append(lines[line_index + 1])
                if line_index + 2 < len(lines):
                    header_lines.append(lines[line_index + 2])
                header_text = " ".join(header_lines)
                labels = _infer_labels(header_text)
                target_index = select_target_label(labels, target_year)
                in_table = True
                line_index += 1
                continue

            if not in_table:
                line_index += 1
                continue

            if not line.strip() or line.strip().lower().startswith("total"):
                line_index += 1
                continue

            columns = split_columns(line)
            if len(columns) < 3:
                line_index += 1
                continue
            match = CODE_RE.match(columns[0])
            code = ""
            desc = ""
            amount_cols = []
            if match:
                code = match.group(1)
                desc = match.group(2).strip()
                amount_cols = columns[1:]
            else:
                code_only = CODE_ONLY_RE.match(columns[0])
                if not code_only:
                    line_index += 1
                    continue
                code = code_only.group(1)
                if len(columns) < 3:
                    line_index += 1
                    continue
                desc = columns[1].strip()
                amount_cols = columns[2:]

            if not labels or target_index is None:
                line_index += 1
                continue
            if not labels or target_index is None:
                line_index += 1
                continue
            if len(amount_cols) >= len(labels):
                amount_cols = amount_cols[-len(labels) :]
            if len(amount_cols) < len(labels):
                line_index += 1
                continue
            if target_index >= len(amount_cols):
                line_index += 1
                continue
            amount_value = parse_amount(amount_cols[target_index])
            if amount_value is None:
                line_index += 1
                continue

            rows.append(
                {
                    "code": code,
                    "description": desc,
                    "amount": ExtractedField.with_value(
                        amount_value,
                        provenance=[Provenance(page=page_index, line_text=line.strip())],
                    ),
                }
            )

            line_index += 1

    return rows


def _infer_labels(header_text: str) -> list[str]:
    lower = re.sub(r"\s+", " ", header_text.lower())
    matches: list[tuple[int, str]] = []
    patterns = [
        (r"(20\d{2})\s+original\s+budget", "original_budget"),
        (r"(20\d{2})\s+revised\s+budget", "revised_budget"),
        (r"(20\d{2})\s+approved\s+budget", "approved_budget"),
        (r"(20\d{2})\s+performance", "performance"),
    ]
    for pattern, label in patterns:
        for match in re.finditer(pattern, lower):
            year = match.group(1)
            matches.append((match.start(), f"{year}_{label}"))
    if "approved" in lower and not any("approved_budget" in label for _, label in matches):
        matches.append((len(lower), "2025_approved_budget"))
    if "revised" in lower and not any("revised_budget" in label for _, label in matches):
        matches.append((len(lower), "2024_revised_budget"))
    if "original" in lower and not any("original_budget" in label for _, label in matches):
        matches.append((len(lower), "2024_original_budget"))
    if "performance" in lower and not any("performance" in label for _, label in matches):
        matches.append((len(lower), "2024_performance"))
    matches.sort(key=lambda item: item[0])
    labels: list[str] = []
    seen = set()
    for _, label in matches:
        if label in seen:
            continue
        labels.append(label)
        seen.add(label)
    return labels
