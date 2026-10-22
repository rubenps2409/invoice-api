"""Quality check against the REAL model. Excluded from normal runs.

uv run pytest -m eval -s
"""

import pytest

from evals.runner import format_repeated, mean, run_eval_repeated, save_report
from invoice_api.config import settings
from invoice_api.services.extraction import get_extractor

pytestmark = pytest.mark.eval

# Tune after the first real run, then keep them as a floor against regressions.
MIN_OVERALL_FIELD_ACCURACY = 0.90
MIN_INVOICE_ACCURACY = 0.75
MIN_REFUSAL_ACCURACY = 0.50


RUNS = 3  # the model is not deterministic: judge the average, not one lucky run


@pytest.mark.skipif(settings.ANTHROPIC_API_KEY is None, reason="ANTHROPIC_API_KEY is not set")
def test_extraction_quality_with_the_real_model():
    report = run_eval_repeated(get_extractor(), runs=RUNS)
    print("\n" + format_repeated(report))
    save_report(report)

    assert mean(report.field_accuracies()) >= MIN_OVERALL_FIELD_ACCURACY
    assert mean(report.invoice_accuracies()) >= MIN_INVOICE_ACCURACY
    assert mean(report.refusal_accuracies()) >= MIN_REFUSAL_ACCURACY
