from __future__ import annotations

import re
from typing import Optional

from engine.economic import NUM_RE, parse_amount
from engine.schema import ExtractedField, Provenance, RevenueRow


RECEIPT_HEADER_RE = re.compile(r"Receipt Description", re.IGNORECASE)
ADMIN_RE = re.compile(r"(?<!\d)(\d{10,14})(?!\d)\s*-\s*([^\d]{2,80})")
ECON_RE = re.compile(r"(?<!\d)(\d{6,8})(?!\d)\s*-\s*([^\d]{2,80})")
FUND_RE = re.compile(r"(?<!\d)(\d{2,6})(?!\d)\s*-\s*([^\d]{2,80})")
AMOUNT_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+")


def extract_receipts(
    pages: list[str],
    target_year: str,
) -> list[RevenueRow]:
    rows: list[RevenueRow] = []
    labels: list[str] = []
    target_index: Optional[int] = None
    in_receipt_table = False

    for page_index, page_text in enumerate(pages, start=1):
        lines = page_text.splitlines()
        line_index = 0
        in_receipt_table = False
        while line_index < len(lines):
            line = lines[line_index]
            if RECEIPT_HEADER_RE.search(line):
                header_lines = []
                if line_index - 1 >= 0:
                    header_lines.append(lines[line_index - 1])
                header_lines.append(line)
                for offset in (1, 2):
                    if line_index + offset < len(lines):
                        header_lines.append(lines[line_index + offset])
                header_text = " ".join(header_lines)
                labels = _infer_receipt_labels(header_text)
                target_index = _select_label_index(labels, target_year)
                in_receipt_table = True
                line_index += 1
                continue

            if not in_receipt_table:
                line_index += 1
                continue

            if not line.strip():
                line_index += 1
                continue
            if line.strip().lower().startswith("total"):
                line_index += 1
                continue

            if target_index is None or not labels:
                line_index += 1
                continue

            combined_lines = [line]
            for offset in (1, 2):
                if line_index + offset < len(lines):
                    combined_lines.append(lines[line_index + offset])

            parsed_row = _parse_receipt_block(" ".join(combined_lines))
            if not parsed_row:
                line_index += 1
                continue

            receipt_desc, admin_parsed, econ_parsed, fund_parsed, amount_cols = parsed_row

            if len(amount_cols) < len(labels):
                line_index += 1
                continue
            amount_cols = amount_cols[-len(labels) :]
            if target_index >= len(amount_cols):
                line_index += 1
                continue
            amount_value = parse_amount(amount_cols[target_index])
            if amount_value is None:
                line_index += 1
                continue

            rows.append(
                RevenueRow(
                    code=ExtractedField.with_value(econ_parsed.group(1)),
                    category=ExtractedField.with_value(receipt_desc),
                    subcategory=ExtractedField.null("not_extracted"),
                    amount=ExtractedField.with_value(
                        amount_value,
                        provenance=[Provenance(page=page_index, line_text=line.strip())],
                    ),
                    classification=ExtractedField.with_value("receipt"),
                    administrative_code=(
                        ExtractedField.with_value(admin_parsed.group(1))
                        if admin_parsed
                        else ExtractedField.null("not_extracted")
                    ),
                    administrative_description=(
                        ExtractedField.with_value(_clean_desc(admin_parsed.group(2)))
                        if admin_parsed
                        else ExtractedField.null("not_extracted")
                    ),
                    fund_code=ExtractedField.with_value(fund_parsed.group(1)),
                    fund_description=ExtractedField.with_value(_clean_desc(fund_parsed.group(2))),
                    page=page_index,
                    line_text=line.strip(),
                )
            )

            line_index += 1

    return rows


def _parse_receipt_block(
    text: str,
) -> tuple[str, Optional[re.Match], re.Match, re.Match, list[str]] | None:
    econ_matches = list(ECON_RE.finditer(text))
    fund_matches = list(FUND_RE.finditer(text))
    admin_matches = list(ADMIN_RE.finditer(text))
    if not econ_matches or not fund_matches:
        return None

    econ_match = min(econ_matches, key=lambda m: m.start())
    fund_after = [m for m in fund_matches if m.start() > econ_match.end()]
    fund_match = min(fund_after, key=lambda m: m.start()) if fund_after else fund_matches[-1]

    admin_match = None
    if admin_matches:
        admin_match = max(admin_matches, key=lambda m: len(m.group(1)))

    receipt_desc = text[: econ_match.start()].strip()
    if len(receipt_desc) < 6:
        return None
    if re.search(r"\d", receipt_desc):
        return None
    amounts = AMOUNT_RE.findall(text[fund_match.end() :])
    if not amounts:
        return None
    return receipt_desc, admin_match, econ_match, fund_match, amounts


def _infer_receipt_labels(header_text: str) -> list[str]:
    lower = re.sub(r"\s+", " ", header_text.lower())
    matches: list[tuple[int, str]] = []
    patterns = [
        (r"(20\d{2})\s+approved(?:\s+budget)?", "approved_budget"),
        (r"(20\d{2})\s+revised(?:\s+budget)?", "revised_budget"),
        (r"(20\d{2})\s+original(?:\s+budget)?", "original_budget"),
        (r"(20\d{2})\s+final(?:\s+budget)?", "final_budget"),
        (r"(20\d{2})\s+performance", "performance"),
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


def _select_label_index(labels: list[str], target_year: str) -> Optional[int]:
    if not labels:
        return None
    for idx, label in enumerate(labels):
        if label.startswith(target_year) and "approved" in label:
            return idx
    for idx, label in enumerate(labels):
        if label.startswith(target_year):
            return idx
    return None


def _clean_desc(text: str) -> str:
    cleaned = re.split(r"\s{2,}", text.strip())[0]
    return cleaned
