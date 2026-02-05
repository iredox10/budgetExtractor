from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from engine.schema import ExtractedField, ExtractionResult


def build_app_output(
    result: ExtractionResult,
    functional_rows: list[dict[str, object]] | None = None,
    sections: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "metadata": _flatten_metadata(result),
        "budget_totals": _flatten_budget_totals(result),
        "counters": _build_counters(result),
        "revenue_breakdown": [_flatten_revenue(row) for row in result.revenue_breakdown],
        "expenditure_economic": [
            _flatten_economic(row) for row in result.expenditure_economic
        ],
        "mda": [_flatten_mda(row) for row in result.expenditure_mda],
        "administrative_units": [
            _flatten_admin_unit(row) for row in result.administrative_units
        ],
        "programme_projects": [
            _flatten_programme(row) for row in result.programme_projects
        ],
        "sectors": _build_sectors(result, functional_rows or []),
        "sections": sections or {},
        "errors": [
            {"code": error.code, "message": error.message} for error in result.errors
        ],
    }


def _field_value(field: ExtractedField | None):
    if field is None:
        return None
    return field.value


def _flatten_metadata(result: ExtractionResult) -> dict[str, object]:
    metadata = result.metadata
    return {
        "state_name": _field_value(metadata.state_name),
        "state_code": _field_value(metadata.state_code),
        "budget_year": _field_value(metadata.budget_year),
        "document_title": _field_value(metadata.document_title),
        "source_file_name": metadata.source_file_name,
        "page_count": metadata.page_count,
        "currency": _field_value(metadata.currency),
        "extraction_timestamp": metadata.extraction_timestamp,
        "engine_version": metadata.engine_version,
    }


def _flatten_budget_totals(result: ExtractionResult) -> dict[str, object]:
    totals = result.budget_totals
    return {
        "total_budget": _field_value(totals.total_budget),
        "capital_expenditure_total": _field_value(totals.capital_expenditure_total),
        "recurrent_expenditure_total": _field_value(totals.recurrent_expenditure_total),
        "revenue_total": _field_value(totals.revenue_total),
        "financing_total": _field_value(totals.financing_total),
        "budget_summary_text": _field_value(totals.budget_summary_text),
    }


def _flatten_amounts(items) -> dict[str, float | None]:
    return {item.label: _field_value(item.amount) for item in items}


def _flatten_admin_unit(unit) -> dict[str, object]:
    return {
        "parent_code": _field_value(unit.parent_code),
        "parent_name": _field_value(unit.parent_name),
        "unit_code": _field_value(unit.unit_code),
        "unit_name": _field_value(unit.unit_name),
        "amounts": _flatten_amounts(unit.amounts),
        "page": unit.page,
        "line_text": unit.line_text,
        "table_type": unit.table_type,
    }


def _flatten_mda(mda) -> dict[str, object]:
    return {
        "mda_code": _field_value(mda.mda_code),
        "mda_name": _field_value(mda.mda_name),
        "recurrent_amount": _field_value(mda.recurrent_amount),
        "capital_amount": _field_value(mda.capital_amount),
        "total_amount": _field_value(mda.total_amount),
        "administrative_units": [
            _flatten_admin_unit(unit) for unit in mda.administrative_units
        ],
        "page": mda.page,
        "line_text": mda.line_text,
    }


def _flatten_revenue(row) -> dict[str, object]:
    return {
        "code": _field_value(row.code),
        "category": _field_value(row.category),
        "subcategory": _field_value(row.subcategory),
        "amount": _field_value(row.amount),
        "classification": _field_value(row.classification),
        "administrative_code": _field_value(row.administrative_code),
        "administrative_description": _field_value(row.administrative_description),
        "fund_code": _field_value(row.fund_code),
        "fund_description": _field_value(row.fund_description),
        "page": row.page,
        "line_text": row.line_text,
    }


def _flatten_economic(row) -> dict[str, object]:
    return {
        "code": _field_value(row.code),
        "category": _field_value(row.category),
        "subcategory": _field_value(row.subcategory),
        "amount": _field_value(row.amount),
        "page": row.page,
        "line_text": row.line_text,
    }


def _flatten_programme(row) -> dict[str, object]:
    return {
        "sector": _field_value(row.sector),
        "objective": _field_value(row.objective),
        "programme_code": _field_value(row.programme_code),
        "programme": _field_value(row.programme),
        "project_name": _field_value(row.project_name),
        "economic_code": _field_value(row.economic_code),
        "economic_description": _field_value(row.economic_description),
        "function_code": _field_value(row.function_code),
        "function_description": _field_value(row.function_description),
        "location_code": _field_value(row.location_code),
        "location_description": _field_value(row.location_description),
        "amount": _field_value(row.amount),
        "amounts": _flatten_amounts(row.amounts),
        "amount_labels": list(row.amount_labels),
        "funding_source": _field_value(row.funding_source),
        "page": row.page,
        "line_text": row.line_text,
    }


def _build_counters(result: ExtractionResult) -> dict[str, object]:
    totals = _flatten_budget_totals(result)
    counters = {
        "total_budget": totals.get("total_budget"),
        "capital_expenditure_total": totals.get("capital_expenditure_total"),
        "recurrent_expenditure_total": totals.get("recurrent_expenditure_total"),
        "revenue_total": totals.get("revenue_total"),
        "financing_total": totals.get("financing_total"),
        "igr_total": _compute_igr(result),
    }
    return counters


def _compute_igr(result: ExtractionResult) -> float | None:
    candidates = []
    for row in result.revenue_breakdown:
        name = (row.category.value or "") + " " + (row.subcategory.value or "")
        name = name.lower()
        if "igr" in name or "independent" in name or "internally" in name:
            if row.amount.value is not None:
                candidates.append(float(row.amount.value))
    if not candidates:
        return None
    return sum(candidates)


def _build_sectors(
    result: ExtractionResult,
    functional_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    if functional_rows:
        sectors = []
        for row in functional_rows:
            amount = _field_value(row["amount"])
            if amount is None:
                continue
            sectors.append(
                {
                    "name": row["description"],
                    "amount": amount,
                    "row_count": 1,
                    "source": "functional_classification",
                }
            )
        return sectors

    sector_totals: dict[str, float] = defaultdict(float)
    row_counts: dict[str, int] = defaultdict(int)

    for row in result.programme_projects:
        amount = row.amount.value
        if amount is None:
            continue
        sector_name = _sector_from_function(
            row.function_code.value,
            row.function_description.value,
        )
        sector_totals[sector_name] += float(amount)
        row_counts[sector_name] += 1

    sectors = []
    for name, total in sorted(sector_totals.items()):
        sectors.append(
            {
                "name": name,
                "amount": total,
                "row_count": row_counts[name],
                "source": "programme_function",
            }
        )
    return sectors


def _sector_from_function(function_code: str | None, function_desc: str | None) -> str:
    if function_code:
        prefix = function_code[:2]
        code_map = {
            "70": "General Public Services",
            "71": "Defense/Public Order",
            "72": "Economic Affairs",
            "73": "Environment",
            "74": "Housing/Community Amenities",
            "75": "Health",
            "76": "Recreation/Culture/Religion",
            "77": "Education",
            "78": "Social Protection",
        }
        if prefix in code_map:
            return code_map[prefix]

    if not function_desc:
        return "Other"
    text = function_desc.lower()
    mapping = [
        ("Education", ["education", "school", "secondary", "primary"]),
        ("Health", ["health", "hospital", "medical"]),
        ("Agriculture", ["agriculture", "fisher", "livestock"]),
        ("Water", ["water", "sanitation"]),
        ("Transport", ["transport", "road", "rail", "aviation"]),
        ("Energy", ["energy", "power", "electric"]),
        ("Environment", ["environment", "climate", "waste"]),
        ("Housing", ["housing", "community amenities"]),
        ("Social Protection", ["social protection", "welfare", "poverty"]),
        ("Defense/Public Order", ["security", "public order", "safety", "defence"]),
        ("Economic Affairs", ["economic affairs", "commerce", "industry", "labour"]),
        ("General Public Services", ["general services", "administration", "legislature"]),
        ("Recreation/Culture", ["recreation", "culture", "religion"]),
    ]
    for sector, keywords in mapping:
        if any(keyword in text for keyword in keywords):
            return sector
    return "Other"
