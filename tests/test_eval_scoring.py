import json
from decimal import Decimal

import pytest

from evals.cases import CASES, EvalCase
from evals.runner import (
    format_repeated,
    format_report,
    run_eval,
    run_eval_repeated,
    save_report,
)
from evals.scoring import FIELDS, score_case, summarize
from invoice_api.schemas.extraction import ExtractedInvoice
from invoice_api.services.extraction import (
    Attempt,
    AttemptOutcome,
    ExtractionInvalidOutput,
    ExtractionResult,
    ExtractionTimeout,
)

CASE = EvalCase(
    id="c1",
    description="d",
    text="text",
    expected={
        "supplier_name": "Acme S.L.",
        "supplier_tax_id": "B12345678",
        "invoice_number": "A-1",
        "issue_date": "2026-03-15",
        "base_amount": "100.00",
        "tax_amount": "21.00",
        "total_amount": "121.00",
        "category_name": "Utilities",
    },
)
REFUSAL = EvalCase(id="r1", description="d", text="hi", expected=None)


def invoice(**overrides) -> ExtractedInvoice:
    data = {**(CASE.expected or {}), **overrides}
    return ExtractedInvoice.model_validate(data)


# --- score_case -------------------------------------------------------------


def test_a_perfect_extraction_scores_every_field():
    score = score_case(CASE, invoice())

    assert score.correct
    assert score.field_results == dict.fromkeys(FIELDS, True)


@pytest.mark.parametrize("wrong", [None, "A98765432"], ids=["missing", "other-company"])
def test_a_wrong_or_missing_tax_id_is_reported(wrong):
    score = score_case(CASE, invoice(supplier_tax_id=wrong))

    assert not score.correct
    assert [f for f, ok in score.field_results.items() if not ok] == ["supplier_tax_id"]
    assert score.mismatches == {"supplier_tax_id": ("B12345678", str(wrong))}


def test_an_invented_tax_id_is_reported_when_none_was_printed():
    case = EvalCase(
        id="c2",
        description="d",
        text="t",
        expected={**(CASE.expected or {}), "supplier_tax_id": None},
    )

    score = score_case(case, invoice(supplier_tax_id="B12345678"))

    assert not score.correct
    assert score.mismatches == {"supplier_tax_id": ("None", "B12345678")}


def test_each_wrong_field_is_reported():
    wrong = invoice(
        invoice_number="B-2",
        base_amount="90.00",
        tax_amount="31.00",
        category_name=None,
    )

    score = score_case(CASE, wrong)

    assert not score.correct
    failed = {f for f, ok in score.field_results.items() if not ok}
    assert failed == {"invoice_number", "base_amount", "tax_amount", "category_name"}


def test_mismatches_record_expected_and_actual_values():
    score = score_case(CASE, invoice(issue_date="2026-11-03", category_name="Marketing"))

    assert score.mismatches == {
        "issue_date": ("2026-03-15", "2026-11-03"),
        "category_name": ("Utilities", "Marketing"),
    }


def test_a_correct_extraction_has_no_mismatches():
    assert score_case(CASE, invoice()).mismatches == {}


def test_the_printed_report_shows_expected_and_actual_values():
    class WrongDate:
        model = "fake-model"

        def extract(self, text, categories):
            case = next(c for c in CASES if c.text == text)
            if case.expected is None:
                raise ExtractionInvalidOutput("no invoice", [])
            data = {**case.expected, "issue_date": "2000-01-01"}
            return ExtractionResult(ExtractedInvoice.model_validate(data), [])

    text = format_report(run_eval(WrongDate()))

    assert "issue_date: expected '2026-" in text
    assert "got '2000-01-01'" in text


def test_supplier_comparison_ignores_case_and_surrounding_spaces():
    assert score_case(CASE, invoice(supplier_name="ACME s.l.")).correct


def test_amounts_are_compared_as_numbers_not_text():
    assert score_case(CASE, invoice(base_amount="100", total_amount="121")).correct


def test_a_failed_extraction_counts_every_field_as_wrong():
    error = ExtractionTimeout("slow", [Attempt(AttemptOutcome.TIMEOUT)])

    score = score_case(CASE, error)

    assert not score.correct
    assert score.field_results == dict.fromkeys(FIELDS, False)
    assert score.error == "ExtractionTimeout"


def test_refusal_cases_are_correct_only_when_the_output_was_invalid():
    refused = ExtractionInvalidOutput("no invoice", [Attempt(AttemptOutcome.INVALID_OUTPUT)])
    timed_out = ExtractionTimeout("slow", [Attempt(AttemptOutcome.TIMEOUT)])

    assert score_case(REFUSAL, refused).correct
    assert not score_case(REFUSAL, timed_out).correct  # an outage is not a refusal
    assert not score_case(REFUSAL, invoice()).correct  # invented an invoice


def test_usage_is_carried_into_the_score():
    score = score_case(CASE, invoice(), attempts=2, input_tokens=900, output_tokens=50)

    assert (score.attempts, score.input_tokens, score.output_tokens) == (2, 900, 50)


# --- summarize --------------------------------------------------------------


def test_summary_computes_field_invoice_and_refusal_accuracy():
    scores = [
        score_case(CASE, invoice()),
        score_case(CASE, invoice(category_name=None)),
        score_case(REFUSAL, ExtractionInvalidOutput("x", [])),
        score_case(REFUSAL, invoice()),
    ]

    summary = summarize(scores)

    assert (summary.extraction_cases, summary.refusal_cases) == (2, 2)
    assert summary.invoice_accuracy == 0.5
    assert summary.refusal_accuracy == 0.5
    assert summary.field_accuracy["category_name"] == 0.5
    assert summary.field_accuracy["total_amount"] == 1.0
    # Two invoices, one wrong field among all of them.
    total_fields = 2 * len(FIELDS)
    assert summary.overall_field_accuracy == pytest.approx((total_fields - 1) / total_fields)


def test_summary_without_refusal_cases_has_no_refusal_accuracy():
    assert summarize([score_case(CASE, invoice())]).refusal_accuracy is None


# --- run_eval with a scripted extractor -------------------------------------


class PerfectExtractor:
    """Answers every case with its expected value (refuses the refusal cases)."""

    model = "fake-model"

    def extract(self, text, categories):
        case = next(c for c in CASES if c.text == text)
        attempt = Attempt(AttemptOutcome.OK, input_tokens=1000, output_tokens=100)
        if case.expected is None:
            raise ExtractionInvalidOutput(
                "no invoice", [Attempt(AttemptOutcome.INVALID_OUTPUT, 800, 20)]
            )
        return ExtractionResult(ExtractedInvoice.model_validate(case.expected), [attempt])


class BrokenExtractor:
    model = "fake-model"

    def extract(self, text, categories):
        raise ExtractionTimeout("slow", [Attempt(AttemptOutcome.TIMEOUT)])


def test_a_perfect_extractor_scores_one_hundred_percent():
    report = run_eval(PerfectExtractor())

    assert report.summary.invoice_accuracy == 1.0
    assert report.summary.overall_field_accuracy == 1.0
    assert report.summary.refusal_accuracy == 1.0
    assert all(s.correct for s in report.scores)


def test_report_adds_up_tokens_and_estimates_the_cost():
    report = run_eval(PerfectExtractor())

    extraction = sum(1 for c in CASES if c.expected is not None)
    refusals = len(CASES) - extraction
    assert report.input_tokens == extraction * 1000 + refusals * 800
    assert report.output_tokens == extraction * 100 + refusals * 20
    assert report.cost_usd > Decimal(0)


def test_a_broken_extractor_scores_zero_without_crashing():
    report = run_eval(BrokenExtractor())

    assert report.summary.invoice_accuracy == 0.0
    assert report.summary.refusal_accuracy == 0.0
    assert {s.error for s in report.scores} == {"ExtractionTimeout"}


def test_saved_report_is_json_and_never_contains_invoice_texts(tmp_path):
    report = run_eval(PerfectExtractor())

    path = save_report(report, tmp_path / "out" / "latest.json")
    raw = path.read_text(encoding="utf-8")

    data = json.loads(raw)
    assert data["model"] == "fake-model"
    assert len(data["scores"]) == len(CASES)
    assert all(c.text not in raw for c in CASES)


def test_the_printed_report_lists_failures_and_totals():
    text = format_report(run_eval(BrokenExtractor()))

    assert "FAIL" in text
    assert "ExtractionTimeout" in text
    assert "Estimated cost" in text
    assert "Invoices fully correct: 0.0%" in text


# --- repeated runs ----------------------------------------------------------


class FlakyExtractor:
    """Reads one date wrongly on every other call to the same case."""

    model = "fake-model"
    flaky_case = "es_utility_with_due_date"

    def __init__(self):
        self.calls = 0

    def extract(self, text, categories):
        case = next(c for c in CASES if c.text == text)
        if case.expected is None:
            raise ExtractionInvalidOutput(
                "no invoice", [Attempt(AttemptOutcome.INVALID_OUTPUT)]
            )
        data = dict(case.expected)
        if case.id == self.flaky_case:
            self.calls += 1
            if self.calls % 2 == 0:
                data["issue_date"] = "2026-05-02"
        return ExtractionResult(
            ExtractedInvoice.model_validate(data), [Attempt(AttemptOutcome.OK, 10, 5)]
        )


def test_repeating_a_stable_extractor_passes_every_case_every_time():
    report = run_eval_repeated(PerfectExtractor(), runs=3)

    assert set(report.case_pass_counts().values()) == {3}
    assert report.invoice_accuracies() == [1.0, 1.0, 1.0]


def test_repeated_runs_expose_a_flaky_case():
    report = run_eval_repeated(FlakyExtractor(), runs=4)

    counts = report.case_pass_counts()
    assert counts[FlakyExtractor.flaky_case] == 2
    assert all(n == 4 for case, n in counts.items() if case != FlakyExtractor.flaky_case)
    assert min(report.invoice_accuracies()) < max(report.invoice_accuracies())


def test_the_repeated_report_counts_each_wrong_value():
    report = run_eval_repeated(FlakyExtractor(), runs=4)

    text = format_repeated(report)

    assert "es_utility_with_due_date" in text
    assert "2/4" in text
    assert "not stable" in text
    assert "got '2026-05-02'  (2x)" in text


def test_repeated_report_adds_up_cost_and_tokens():
    single = run_eval(PerfectExtractor())

    report = run_eval_repeated(PerfectExtractor(), runs=3)

    assert report.input_tokens == 3 * single.input_tokens
    assert report.cost_usd == 3 * single.cost_usd


def test_repeated_report_is_saved_as_json(tmp_path):
    report = run_eval_repeated(PerfectExtractor(), runs=2)

    path = save_report(report, tmp_path / "latest.json")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["runs"]) == 2
    assert all(c.text not in path.read_text(encoding="utf-8") for c in CASES)


def test_zero_runs_is_rejected():
    with pytest.raises(ValueError):
        run_eval_repeated(PerfectExtractor(), runs=0)


class RetryingExtractor:
    """Needs a second model call on every other call to one case."""

    model = "fake-model"
    retried_case = "large_amount"

    def __init__(self):
        self.calls = 0

    def extract(self, text, categories):
        case = next(c for c in CASES if c.text == text)
        if case.expected is None:
            raise ExtractionInvalidOutput(
                "no invoice",
                [
                    Attempt(AttemptOutcome.INVALID_OUTPUT),
                    Attempt(AttemptOutcome.INVALID_OUTPUT),
                ],
            )
        attempts = [Attempt(AttemptOutcome.OK, 10, 5)]
        if case.id == self.retried_case:
            self.calls += 1
            if self.calls % 2 == 1:
                attempts.insert(
                    0, Attempt(AttemptOutcome.INVALID_OUTPUT, 10, 5, detail="bad json")
                )
        return ExtractionResult(ExtractedInvoice.model_validate(case.expected), attempts)


def test_retries_that_end_well_are_still_visible():
    report = run_eval_repeated(RetryingExtractor(), runs=4)

    assert set(report.case_pass_counts().values()) == {4}  # all pass...
    retries = report.retry_counts()
    assert retries[RetryingExtractor.retried_case] == 2  # ...but one needed retries
    assert "large_amount" in retries
    assert all(n == 0 for c, n in retries.items() if c != RetryingExtractor.retried_case)
    assert not any(c.startswith("refuse_") for c in retries)  # refusals excluded
    assert "needed a retry in 2/4 runs" in format_repeated(report)


def test_a_stable_extractor_never_reports_retries():
    report = run_eval_repeated(PerfectExtractor(), runs=3)

    assert set(report.retry_counts().values()) == {0}
    assert "retry" not in format_repeated(report)
