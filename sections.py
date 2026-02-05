from __future__ import annotations

import re
from dataclasses import dataclass


SECTION_PATTERNS = [
    ("summary", re.compile(r"Approved Budget Summary|Budget Summary", re.IGNORECASE)),
    (
        "revenue_by_mda",
        re.compile(r"Revenue by MDA", re.IGNORECASE),
    ),
    (
        "revenue_by_economic",
        re.compile(r"Revenue by Economic Classification", re.IGNORECASE),
    ),
    (
        "capital_receipts",
        re.compile(r"Capital Receipts", re.IGNORECASE),
    ),
    (
        "expenditure_by_mda",
        re.compile(r"Expenditure by MDA", re.IGNORECASE),
    ),
    (
        "total_expenditure_admin",
        re.compile(r"Total Expenditure by Administrative Classification", re.IGNORECASE),
    ),
    (
        "personnel_expenditure_admin",
        re.compile(
            r"Personnel Expenditure by Administrative Classification",
            re.IGNORECASE,
        ),
    ),
    (
        "other_recurrent_admin",
        re.compile(
            r"Other Non-Debt Recurrent Expenditure by Administrative Classification",
            re.IGNORECASE,
        ),
    ),
    (
        "debt_service_admin",
        re.compile(
            r"Debt Service Expenditure by Administrative Classification",
            re.IGNORECASE,
        ),
    ),
    (
        "capital_expenditure_admin",
        re.compile(
            r"Capital Expenditure by Administrative Classification",
            re.IGNORECASE,
        ),
    ),
    (
        "expenditure_by_economic",
        re.compile(r"Expenditure by Economic Classification", re.IGNORECASE),
    ),
    (
        "total_expenditure_functional",
        re.compile(r"Total Expenditure by Functional Classification", re.IGNORECASE),
    ),
    (
        "personnel_expenditure_functional",
        re.compile(
            r"Personnel Expenditure by Functional Classification",
            re.IGNORECASE,
        ),
    ),
    (
        "other_recurrent_functional",
        re.compile(
            r"Other Non-Debt Recurrent Expenditure by Functional Classification",
            re.IGNORECASE,
        ),
    ),
    (
        "debt_service_functional",
        re.compile(
            r"Debt Service Expenditure by Functional Classification",
            re.IGNORECASE,
        ),
    ),
    (
        "capital_expenditure_functional",
        re.compile(
            r"Capital Expenditure by Functional Classification",
            re.IGNORECASE,
        ),
    ),
    (
        "expenditure_by_location",
        re.compile(r"Total Expenditure by Location", re.IGNORECASE),
    ),
    (
        "expenditure_by_programme",
        re.compile(
            r"Total Expenditure by Programme \(Sector, Objective and Programme\)",
            re.IGNORECASE,
        ),
    ),
    (
        "basic_education_admin",
        re.compile(r"Basic Education Expenditure by Administrative Classification", re.IGNORECASE),
    ),
    (
        "basic_education_economic",
        re.compile(r"Basic Education Expenditure by Economic Classification", re.IGNORECASE),
    ),
    (
        "primary_health_admin",
        re.compile(r"Primary Health Expenditure by Administrative Classification", re.IGNORECASE),
    ),
    (
        "primary_health_economic",
        re.compile(r"Primary Health Expenditure by Economic Classification", re.IGNORECASE),
    ),
    (
        "capital_project",
        re.compile(r"Capital Expenditure by Project", re.IGNORECASE),
    ),
    (
        "revenue_expenditure_fund",
        re.compile(r"Revenue and Expenditure by Fund", re.IGNORECASE),
    ),
]


@dataclass
class SectionHit:
    key: str
    title: str
    page: int


def detect_sections(pages: list[str]) -> list[SectionHit]:
    hits: list[SectionHit] = []
    for page_index, page_text in enumerate(pages, start=1):
        lines = page_text.splitlines()
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            for key, pattern in SECTION_PATTERNS:
                if pattern.search(stripped):
                    hits.append(SectionHit(key=key, title=stripped, page=page_index))
                    break
    return hits


def section_order(hits: list[SectionHit]) -> list[str]:
    ordered = []
    seen = set()
    for hit in sorted(hits, key=lambda h: (h.page, h.key)):
        if hit.key in seen:
            continue
        ordered.append(hit.key)
        seen.add(hit.key)
    return ordered


def classification_scheme(hits: list[SectionHit]) -> list[str]:
    scheme = []
    if any(hit.key.endswith("_by_mda") or hit.key.endswith("_admin") for hit in hits):
        scheme.append("administrative")
    if any("economic" in hit.key for hit in hits):
        scheme.append("economic")
    if any("functional" in hit.key for hit in hits):
        scheme.append("functional")
    if any("location" in hit.key for hit in hits):
        scheme.append("location")
    if any("programme" in hit.key for hit in hits):
        scheme.append("programme")
    if any("project" in hit.key for hit in hits):
        scheme.append("project")
    if any("fund" in hit.key for hit in hits):
        scheme.append("fund")
    return scheme
