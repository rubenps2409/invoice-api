"""Run the extraction eval and report accuracy, tokens and estimated cost.

    uv run python -m evals.runner

It calls the REAL model, so it needs ANTHROPIC_API_KEY and costs a few cents.
"""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from evals.cases import CASES, EvalCase
from evals.scoring import CaseScore, Summary, score_case, summarize
from invoice_api.config import settings
from invoice_api.services.extraction import Attempt, ExtractionError, ExtractionResult
from invoice_api.services.llm_usage import estimate_cost_usd

RESULTS_FILE = Path(__file__).parent / "results" / "latest.json"


class Extractor(Protocol):
    @property
    def model(self) -> str: ...

    def extract(self, text: str, categories: tuple[str, ...]) -> ExtractionResult: ...


@dataclass(frozen=True)
class EvalReport:
    model: str
    run_at: str
    scores: list[CaseScore]
    summary: Summary
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal

    def to_dict(self) -> dict:
        # Only ids and scores: never the invoice texts.
        data = asdict(self)
        data["cost_usd"] = str(self.cost_usd)
        return data


def run_eval(extractor: Extractor, cases: tuple[EvalCase, ...] = CASES) -> EvalReport:
    scores: list[CaseScore] = []
    for case in cases:
        attempts: list[Attempt]
        try:
            result = extractor.extract(case.text, case.categories)
            outcome, attempts = result.invoice, result.attempts
        except ExtractionError as exc:
            outcome, attempts = exc, exc.attempts
        scores.append(
            score_case(
                case,
                outcome,
                attempts=len(attempts),
                input_tokens=sum(a.input_tokens for a in attempts),
                output_tokens=sum(a.output_tokens for a in attempts),
            )
        )

    input_tokens = sum(s.input_tokens for s in scores)
    output_tokens = sum(s.output_tokens for s in scores)
    return EvalReport(
        model=extractor.model,
        run_at=datetime.now(UTC).isoformat(timespec="seconds"),
        scores=scores,
        summary=summarize(scores),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_cost_usd(
            input_tokens,
            output_tokens,
            input_price_per_mtok=settings.LLM_INPUT_PRICE_PER_MTOK,
            output_price_per_mtok=settings.LLM_OUTPUT_PRICE_PER_MTOK,
        ),
    )


def format_report(report: EvalReport) -> str:
    s = report.summary
    lines = [
        f"Model: {report.model}   Run: {report.run_at}",
        "",
        f"{'case':<36} {'result':<8} detail",
    ]
    for score in report.scores:
        wrong = [f for f, ok in score.field_results.items() if not ok]
        if score.correct:
            detail = "refused as expected" if score.expects_refusal else ""
        elif score.error:
            detail = f"error: {score.error}"
        else:
            detail = "wrong: " + ", ".join(wrong)
        lines.append(
            f"{score.case_id:<36} {'OK' if score.correct else 'FAIL':<8} {detail}"
        )

    lines += ["", "Field accuracy (extraction cases):"]
    lines += [f"  {f:<16} {acc:6.1%}" for f, acc in s.field_accuracy.items()]
    lines += [
        f"  {'ALL FIELDS':<16} {s.overall_field_accuracy:6.1%}",
        "",
        f"Invoices fully correct: {s.invoice_accuracy:.1%} of {s.extraction_cases}",
    ]
    if s.refusal_accuracy is not None:
        lines.append(
            f"Refusals correct:       {s.refusal_accuracy:.1%} of {s.refusal_cases}"
        )
    lines.append(
        f"Tokens: {report.input_tokens} in / {report.output_tokens} out   "
        f"Estimated cost: ${report.cost_usd}"
    )
    return "\n".join(lines)


def save_report(report: EvalReport, path: Path = RESULTS_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def main() -> None:
    from invoice_api.services.extraction import ExtractionNotConfigured, get_extractor

    try:
        extractor = get_extractor()
    except ExtractionNotConfigured:
        raise SystemExit("Set ANTHROPIC_API_KEY in .env to run the eval.") from None

    report = run_eval(extractor)
    print(format_report(report))
    print(f"\nSaved to {save_report(report)}")


if __name__ == "__main__":
    main()