from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from engine.extract_text import extract_fulltext, get_page_count, split_pages
from engine.metrics import compute_page_metrics
from engine.schema import (
    AppropriationLaw,
    BudgetTotals,
    DocumentMetadata,
    ExtractionError,
    ExtractionResult,
    ExtractedField,
)
from engine.utils import ensure_dir
from engine.validation import validate_page_count


ENGINE_VERSION = "0.1.0"


def build_default_result(
    pdf_path: Path,
    page_count: int,
    errors: list[ExtractionError],
) -> ExtractionResult:
    not_extracted = "not_extracted"

    metadata = DocumentMetadata(
        state_name=ExtractedField.null(not_extracted),
        state_code=ExtractedField.null(not_extracted),
        budget_year=ExtractedField.null(not_extracted),
        document_title=ExtractedField.null(not_extracted),
        source_file_name=pdf_path.name,
        page_count=page_count,
        currency=ExtractedField.null(not_extracted),
        extraction_timestamp=datetime.utcnow().isoformat() + "Z",
        engine_version=ENGINE_VERSION,
    )

    budget_totals = BudgetTotals(
        total_budget=ExtractedField.null(not_extracted),
        capital_expenditure_total=ExtractedField.null(not_extracted),
        recurrent_expenditure_total=ExtractedField.null(not_extracted),
        revenue_total=ExtractedField.null(not_extracted),
        financing_total=ExtractedField.null(not_extracted),
        budget_summary_text=ExtractedField.null(not_extracted),
    )

    appropriation_law = AppropriationLaw(
        law_text=ExtractedField.null(not_extracted),
        page_range=ExtractedField.null(not_extracted),
        total_amount=ExtractedField.null(not_extracted),
    )

    status = "failed" if errors else "ok"

    return ExtractionResult(
        status=status,
        errors=errors,
        metadata=metadata,
        budget_totals=budget_totals,
        revenue_breakdown=[],
        expenditure_economic=[],
        expenditure_mda=[],
        programme_projects=[],
        appropriation_law=appropriation_law,
        assumptions=[],
    )


def run_pipeline(pdf_path: Path, output_dir: Path, overwrite: bool = False) -> Path:
    if not pdf_path.exists():
        raise FileNotFoundError(f"Input PDF not found: {pdf_path}")

    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Output directory not empty: {output_dir}. Use --overwrite to continue."
        )

    ensure_dir(output_dir)

    text_path = output_dir / "text.txt"
    metrics_path = output_dir / "page_metrics.json"
    output_path = output_dir / "output.json"

    errors: list[ExtractionError] = []

    page_count, page_error = get_page_count(pdf_path)
    if page_error:
        errors.append(ExtractionError(code="pdfinfo_failed", message=page_error))

    if not errors:
        extract_error = extract_fulltext(pdf_path, text_path)
        if extract_error:
            errors.append(
                ExtractionError(code="pdftotext_failed", message=extract_error)
            )

    pages: list[str] = []
    if not errors and text_path.exists():
        text = text_path.read_text(encoding="utf-8", errors="replace")
        pages = split_pages(text)
        metrics = compute_page_metrics(pages)
        metrics_path.write_text(
            json.dumps(
                {
                    "file": pdf_path.name,
                    "pages_expected": page_count,
                    "pages_extracted": len(pages),
                    "per_page": metrics,
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )

        validation_errors = validate_page_count(page_count, len(pages))
        errors.extend(
            ExtractionError(code=err.code, message=err.message)
            for err in validation_errors
        )

    result = build_default_result(pdf_path, page_count, errors)
    output_path.write_text(
        json.dumps(asdict(result), ensure_ascii=True, indent=2),
        encoding="utf-8",
    )

    return output_path
