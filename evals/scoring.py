from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from evals.cases import EvalCase
from invoice_api.schemas.extraction import ExtractedInvoice
from invoice_api.services.extraction import ExtractionError, ExtractionInvalidOutput

FIELDS = (
    "supplier_name",
    "supplier_tax_id",
    "invoice_number",
    "issue_date",
    "base_amount",
    "tax_amount",
    "withholding_amount",
    "total_amount",
    "currency",
    "category_name",
)


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    expects_refusal: bool
    correct: bool
    field_results: dict[str, bool]  # empty for refusal cases
    error: str | None = None  # exception class name, if the extraction failed
    # field -> (expected, got), only for wrong fields. The data is synthetic.
    mismatches: dict[str, tuple[str, str]] = field(default_factory=dict)
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class Summary:
    extraction_cases: int
    refusal_cases: int
    field_accuracy: dict[str, float]
    overall_field_accuracy: float
    invoice_accuracy: float  # share of invoices with EVERY field right
    refusal_accuracy: float | None  # None when there are no refusal cases


def _same(field: str, expected: object, actual: object) -> bool:
    if field in {"base_amount", "tax_amount", "withholding_amount", "total_amount"}:
        return Decimal(str(expected)) == actual
    if field == "supplier_name":
        return str(expected).strip().casefold() == str(actual).strip().casefold()
    if field == "issue_date":
        return isinstance(actual, date) and str(expected) == actual.isoformat()
    return expected == actual


def _figures(invoice: ExtractedInvoice) -> str:
    """Amounts and currency only: no names and no text of the invoice."""
    return (
        f"base={invoice.base_amount} tax={invoice.tax_amount} "
        f"withholding={invoice.withholding_amount} total={invoice.total_amount} "
        f"currency={invoice.currency}"
    )


def score_case(
    case: EvalCase,
    outcome: ExtractedInvoice | ExtractionError,
    *,
    attempts: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> CaseScore:
    error = type(outcome).__name__ if isinstance(outcome, ExtractionError) else None
    results: dict[str, bool] = {}
    mismatches: dict[str, tuple[str, str]] = {}

    if case.expected is None:
        # The right behaviour is a refusal: the model never produced a valid invoice.
        correct = isinstance(outcome, ExtractionInvalidOutput)
        if isinstance(outcome, ExtractedInvoice):
            # It made up an invoice instead: show the figures it settled on.
            mismatches = {"returned_instead_of_refusing": ("a refusal", _figures(outcome))}
    elif isinstance(outcome, ExtractionError):
        results = dict.fromkeys(FIELDS, False)
        correct = False
    else:
        results = {
            name: _same(name, case.expected[name], getattr(outcome, name)) for name in FIELDS
        }
        mismatches = {
            name: (str(case.expected[name]), str(getattr(outcome, name)))
            for name, ok in results.items()
            if not ok
        }
        correct = all(results.values())

    return CaseScore(
        case_id=case.id,
        expects_refusal=case.expected is None,
        correct=correct,
        field_results=results,
        error=error,
        mismatches=mismatches,
        attempts=attempts,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def summarize(scores: list[CaseScore]) -> Summary:
    extraction = [s for s in scores if not s.expects_refusal]
    refusals = [s for s in scores if s.expects_refusal]

    def share(items: list[bool]) -> float:
        return sum(items) / len(items) if items else 0.0

    field_accuracy = {f: share([s.field_results[f] for s in extraction]) for f in FIELDS}
    return Summary(
        extraction_cases=len(extraction),
        refusal_cases=len(refusals),
        field_accuracy=field_accuracy,
        overall_field_accuracy=share(
            [ok for s in extraction for ok in s.field_results.values()]
        ),
        invoice_accuracy=share([s.correct for s in extraction]),
        refusal_accuracy=share([s.correct for s in refusals]) if refusals else None,
    )
