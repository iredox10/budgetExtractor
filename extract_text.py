from __future__ import annotations

from pathlib import Path

from engine.utils import run_command


def get_page_count(pdf_path: Path) -> tuple[int, str]:
    result = run_command(["pdfinfo", str(pdf_path)])
    if result.returncode != 0:
        return 0, result.stderr.strip() or f"exit {result.returncode}"

    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip()), ""
            except ValueError:
                return 0, "invalid page count in pdfinfo"

    return 0, "page count not found in pdfinfo"


def extract_fulltext(pdf_path: Path, text_path: Path) -> str:
    result = run_command(
        [
            "pdftotext",
            "-layout",
            "-enc",
            "UTF-8",
            str(pdf_path),
            str(text_path),
        ]
    )
    if result.returncode != 0:
        return result.stderr.strip() or f"exit {result.returncode}"
    return ""


def split_pages(text: str) -> list[str]:
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    return pages
