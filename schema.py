from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Optional, TypeVar


T = TypeVar("T")


@dataclass
class Provenance:
    page: int
    line_text: str


@dataclass
class ExtractedField(Generic[T]):
    value: Optional[T]
    reason: Optional[str]
    provenance: list[Provenance] = field(default_factory=list)

    @staticmethod
    def null(reason: str) -> "ExtractedField[T]":
        return ExtractedField(value=None, reason=reason, provenance=[])

    @staticmethod
    def with_value(value: T, provenance: Optional[list[Provenance]] = None) -> "ExtractedField[T]":
        return ExtractedField(value=value, reason=None, provenance=provenance or [])


@dataclass
class DocumentMetadata:
    state_name: ExtractedField[str]
    state_code: ExtractedField[str]
    budget_year: ExtractedField[str]
    document_title: ExtractedField[str]
    source_file_name: str
    page_count: int
    currency: ExtractedField[str]
    extraction_timestamp: str
    engine_version: str


@dataclass
class BudgetTotals:
    total_budget: ExtractedField[float]
    capital_expenditure_total: ExtractedField[float]
    recurrent_expenditure_total: ExtractedField[float]
    revenue_total: ExtractedField[float]
    financing_total: ExtractedField[float]
    budget_summary_text: ExtractedField[str]


@dataclass
class RevenueRow:
    category: ExtractedField[str]
    subcategory: ExtractedField[str]
    amount: ExtractedField[float]
    classification: ExtractedField[str]
    page: Optional[int] = None
    line_text: Optional[str] = None


@dataclass
class EconomicExpenditureRow:
    category: ExtractedField[str]
    subcategory: ExtractedField[str]
    amount: ExtractedField[float]
    page: Optional[int] = None
    line_text: Optional[str] = None


@dataclass
class MdaExpenditureRow:
    mda_code: ExtractedField[str]
    mda_name: ExtractedField[str]
    recurrent_amount: ExtractedField[float]
    capital_amount: ExtractedField[float]
    total_amount: ExtractedField[float]
    page: Optional[int] = None
    line_text: Optional[str] = None


@dataclass
class ProgrammeRow:
    sector: ExtractedField[str]
    programme: ExtractedField[str]
    project_name: ExtractedField[str]
    amount: ExtractedField[float]
    funding_source: ExtractedField[str]
    page: Optional[int] = None
    line_text: Optional[str] = None


@dataclass
class AssumptionRow:
    assumption_name: ExtractedField[str]
    value: ExtractedField[str]
    unit: ExtractedField[str]
    page: Optional[int] = None
    line_text: Optional[str] = None


@dataclass
class AppropriationLaw:
    law_text: ExtractedField[str]
    page_range: ExtractedField[str]
    total_amount: ExtractedField[float]


@dataclass
class ExtractionError:
    code: str
    message: str


@dataclass
class ExtractionResult:
    status: str
    errors: list[ExtractionError]
    metadata: DocumentMetadata
    budget_totals: BudgetTotals
    revenue_breakdown: list[RevenueRow]
    expenditure_economic: list[EconomicExpenditureRow]
    expenditure_mda: list[MdaExpenditureRow]
    programme_projects: list[ProgrammeRow]
    appropriation_law: AppropriationLaw
    assumptions: list[AssumptionRow]
