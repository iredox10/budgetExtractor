from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from engine.admin_units import ParentRow, extract_admin_units
from engine.economic import extract_economic_rows
from engine.extract_text import extract_fulltext, get_page_count, split_pages
from engine.metadata import extract_metadata
from engine.metrics import compute_page_metrics
from engine.normalization import normalize_label
from engine.programme_projects import extract_programme_projects
from engine.receipts import extract_receipts
from engine.review import build_review_report
from engine.app_output import build_app_output
from engine.functional import extract_functional_classification
from engine.schema import (
    AppropriationLaw,
    BudgetTotals,
    DocumentMetadata,
    ExtractionError,
    ExtractionResult,
    ExtractedField,
    MdaExpenditureRow,
)
from engine.summary import extract_budget_summary
from engine.utils import ensure_dir
from engine.validation import (
    validate_admin_unit_codes,
    validate_economic_conflicts,
    validate_economic_rows,
    validate_economic_duplicates,
    validate_economic_hierarchy,
    validate_budget_components,
    validate_global_reconciliation,
    validate_programme_rows,
    validate_metadata_consistency,
    validate_mda_reconciliation,
    validate_page_count,
)


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
        administrative_units=[],
        programme_projects=[],
        appropriation_law=appropriation_law,
        assumptions=[],
    )


def build_mda_groups(
    admin_units: list,
    parent_rows: list[ParentRow],
) -> list[MdaExpenditureRow]:
    parents: dict[str, MdaExpenditureRow] = {}

    for parent in parent_rows:
        if parent.table_type != "expenditure_mda":
            continue
        recurrent = next(
            (item.amount for item in parent.amounts if item.label == "total_recurrent"),
            ExtractedField.null("not_extracted"),
        )
        capital = next(
            (item.amount for item in parent.amounts if item.label == "capital"),
            ExtractedField.null("not_extracted"),
        )
        total = next(
            (item.amount for item in parent.amounts if item.label == "total_expenditure"),
            ExtractedField.null("not_extracted"),
        )
        parents[parent.code] = MdaExpenditureRow(
            mda_code=ExtractedField.with_value(parent.code),
            mda_name=ExtractedField.with_value(parent.name),
            recurrent_amount=recurrent,
            capital_amount=capital,
            total_amount=total,
            administrative_units=[],
            page=parent.page,
            line_text=parent.line_text,
        )

    for unit in admin_units:
        parent_code = unit.parent_code.value
        parent_name = unit.parent_name.value
        if not parent_code or not parent_name:
            continue
        if parent_code not in parents:
            parents[parent_code] = MdaExpenditureRow(
                mda_code=ExtractedField.with_value(parent_code),
                mda_name=ExtractedField.with_value(parent_name),
                recurrent_amount=ExtractedField.null("not_extracted"),
                capital_amount=ExtractedField.null("not_extracted"),
                total_amount=ExtractedField.null("not_extracted"),
                administrative_units=[],
            )
        parents[parent_code].administrative_units.append(unit)

    return [parents[key] for key in sorted(parents.keys())]


def run_pipeline(pdf_path: Path, output_dir: Path, overwrite: bool = False) -> Path:
    if not pdf_path.exists():
        raise FileNotFoundError(f"Input PDF not found: {pdf_path}")

    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Output directory not empty: {output_dir}. Use --overwrite to continue."
        )

    ensure_dir(output_dir)

    log_path = output_dir / "run.log"

    def log(message: str) -> None:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
        print(message)

    text_path = output_dir / "text.txt"
    metrics_path = output_dir / "page_metrics.json"
    output_path = output_dir / "output.json"
    review_path = output_dir / "review.json"
    app_output_path = output_dir / "app_output.json"

    errors: list[ExtractionError] = []
    target_year = ""
    year_match = re.search(r"(20\d{2})", pdf_path.name)
    if year_match:
        target_year = year_match.group(1)

    log("Starting extraction pipeline")
    page_count, page_error = get_page_count(pdf_path)
    if page_error:
        errors.append(ExtractionError(code="pdfinfo_failed", message=page_error))
    else:
        log(f"Detected page count: {page_count}")

    if not errors:
        if text_path.exists() and text_path.stat().st_size > 0:
            log("Using existing text.txt")
        else:
            log("Extracting text with pdftotext")
            extract_error = extract_fulltext(pdf_path, text_path)
            if extract_error:
                errors.append(
                    ExtractionError(code="pdftotext_failed", message=extract_error)
                )

    pages: list[str] = []
    admin_units = []
    parent_rows: list[ParentRow] = []
    revenue_rows = []
    expenditure_rows = []
    programme_rows = []
    budget_totals = None
    summary_context = None
    metadata_fields = None
    mda_rows = []
    receipt_rows = []
    functional_rows = []
    if not errors and text_path.exists():
        text = text_path.read_text(encoding="utf-8", errors="replace")
        pages = split_pages(text)
        if metrics_path.exists():
            log("Using existing page_metrics.json")
        else:
            log("Computing page metrics")
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
        log("Page validation complete")

        metadata_fields = extract_metadata(pdf_path, pages)
        log("Metadata extraction complete")

        admin_units, parent_rows, _ = extract_admin_units(pages)
        errors.extend(
            ExtractionError(code=err.code, message=err.message)
            for err in validate_admin_unit_codes(admin_units)
        )
        errors.extend(
            ExtractionError(code=err.code, message=err.message)
            for err in validate_mda_reconciliation(parent_rows, admin_units)
        )
        mda_rows = build_mda_groups(admin_units, parent_rows)
        log("Administrative units extraction complete")

        if target_year:
            revenue_rows, expenditure_rows, conflicts = extract_economic_rows(
                pages, target_year
            )
            errors.extend(
                ExtractionError(code=err.code, message=err.message)
                for err in validate_economic_rows(revenue_rows, expenditure_rows)
            )
            errors.extend(
                ExtractionError(code=err.code, message=err.message)
                for err in validate_economic_duplicates(revenue_rows, expenditure_rows)
            )
            errors.extend(
                ExtractionError(code=err.code, message=err.message)
                for err in validate_economic_conflicts(conflicts)
            )
            errors.extend(
                ExtractionError(code=err.code, message=err.message)
                for err in validate_economic_hierarchy(revenue_rows, expenditure_rows)
            )
            budget_totals, summary_context = extract_budget_summary(pages, target_year)
            programme_rows = extract_programme_projects(pages, target_year)
            receipt_rows = extract_receipts(pages, target_year)
            functional_rows = extract_functional_classification(pages, target_year)
            log("Economic, programme, and receipt extraction complete")
            errors.extend(
                ExtractionError(code=err.code, message=err.message)
                for err in validate_programme_rows(programme_rows)
            )

            for row in programme_rows:
                if row.sector.value:
                    row.sector = ExtractedField.with_value(
                        normalize_label(row.sector.value),
                        provenance=row.sector.provenance,
                    )
                if row.objective.value:
                    row.objective = ExtractedField.with_value(
                        normalize_label(row.objective.value),
                        provenance=row.objective.provenance,
                    )

            if budget_totals is not None:
                errors.extend(
                    ExtractionError(code=err.code, message=err.message)
                    for err in validate_budget_components(budget_totals)
                )
                errors.extend(
                    ExtractionError(code=err.code, message=err.message)
                    for err in validate_global_reconciliation(
                        budget_totals,
                        revenue_rows,
                        expenditure_rows,
                        mda_rows,
                        programme_rows,
                        "recurrent_revenue" if summary_context.recurrent_revenue else None,
                    )
                )

    result = build_default_result(pdf_path, page_count, errors)
    if metadata_fields:
        result.metadata.state_name = metadata_fields["state_name"]
        result.metadata.state_code = metadata_fields["state_code"]
        result.metadata.budget_year = metadata_fields["budget_year"]
        result.metadata.document_title = metadata_fields["document_title"]
        result.metadata.currency = metadata_fields["currency"]
        errors.extend(
            ExtractionError(code=err.code, message=err.message)
            for err in validate_metadata_consistency(result.metadata, pdf_path)
        )
    if budget_totals is not None:
        result.budget_totals = budget_totals
    result.administrative_units = admin_units
    result.expenditure_mda = mda_rows
    result.revenue_breakdown = revenue_rows
    if receipt_rows:
        result.revenue_breakdown.extend(receipt_rows)
    result.expenditure_economic = expenditure_rows
    result.programme_projects = programme_rows
    output_path.write_text(
        json.dumps(asdict(result), ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    review_path.write_text(
        json.dumps(build_review_report(errors), ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    app_output_path.write_text(
        json.dumps(build_app_output(result, functional_rows), ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    log("Wrote output.json, app_output.json, and review.json")

    return output_path
