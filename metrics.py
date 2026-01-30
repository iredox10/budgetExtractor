from __future__ import annotations

import re


CODE_RE = re.compile(r"^\s*\d{6,}")
COLUMN_RE = re.compile(r"\S\s{2,}\S")


def compute_page_metrics(pages: list[str]) -> list[dict[str, object]]:
    metrics: list[dict[str, object]] = []

    for index, page_text in enumerate(pages, start=1):
        lines = page_text.splitlines()
        nonempty_lines = [line for line in lines if line.strip()]
        nonempty_count = len(nonempty_lines)
        empty_count = len(lines) - nonempty_count

        first_line = nonempty_lines[0].strip() if nonempty_lines else ""
        last_line = nonempty_lines[-1].strip() if nonempty_lines else ""

        char_count = len(page_text.strip())
        digit_count = sum(char.isdigit() for char in page_text)
        letter_count = sum(char.isalpha() for char in page_text)
        digit_ratio = digit_count / max(digit_count + letter_count, 1)

        code_line_count = sum(1 for line in nonempty_lines if CODE_RE.match(line))
        column_line_count = sum(1 for line in nonempty_lines if COLUMN_RE.search(line))

        code_line_ratio = code_line_count / max(nonempty_count, 1)
        column_line_ratio = column_line_count / max(nonempty_count, 1)

        table_like = bool(
            digit_ratio > 0.35 or column_line_ratio > 0.25 or code_line_ratio > 0.2
        )
        low_text = char_count < 80

        metrics.append(
            {
                "page": index,
                "char_count": char_count,
                "nonempty_lines": nonempty_count,
                "empty_lines": empty_count,
                "digit_ratio": round(digit_ratio, 4),
                "code_line_ratio": round(code_line_ratio, 4),
                "column_line_ratio": round(column_line_ratio, 4),
                "table_like": table_like,
                "low_text": low_text,
                "first_line": first_line,
                "last_line": last_line,
            }
        )

    return metrics
