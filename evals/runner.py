"""Run the extraction eval and report accuracy, tokens and estimated cost.

    uv run python -m evals.runner            # one run
    uv run python -m evals.runner --runs 5   # repeat, to measure consistency

It calls the REAL model, so it needs ANTHROPIC_API_KEY and costs a few cents.
Current models have no temperature setting, so two runs can differ: a single
run is an anecdote, several runs are a measurement.
"""

import argparse
import asyncio
import json
from collections import Counter
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

    async def extract(self, text: str, categories: tuple[str, ...]) -> ExtractionResult: ...


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


async def run_eval(extractor: Extractor, cases: tuple[EvalCase, ...] = CASES) -> EvalReport:
    scores: list[CaseScore] = []
    for case in cases:
        attempts: list[Attempt]
        try:
            result = await extractor.extract(case.text, case.categories)
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
        lines.append(f"{score.case_id:<36} {'OK' if score.correct else 'FAIL':<8} {detail}")
        for name, (expected, got) in score.mismatches.items():
            lines.append(f"    {name}: expected {expected!r}, got {got!r}")

    lines += ["", "Field accuracy (extraction cases):"]
    lines += [f"  {f:<16} {acc:6.1%}" for f, acc in s.field_accuracy.items()]
    lines += [
        f"  {'ALL FIELDS':<16} {s.overall_field_accuracy:6.1%}",
        "",
        f"Invoices fully correct: {s.invoice_accuracy:.1%} of {s.extraction_cases}",
    ]
    if s.refusal_accuracy is not None:
        lines.append(f"Refusals correct:       {s.refusal_accuracy:.1%} of {s.refusal_cases}")
    lines.append(
        f"Tokens: {report.input_tokens} in / {report.output_tokens} out   "
        f"Estimated cost: ${report.cost_usd}"
    )
    return "\n".join(lines)


@dataclass(frozen=True)
class RepeatedReport:
    """The same eval run several times, to see how stable the model is."""

    reports: list[EvalReport]

    @property
    def runs(self) -> int:
        return len(self.reports)

    @property
    def model(self) -> str:
        return self.reports[0].model

    @property
    def input_tokens(self) -> int:
        return sum(r.input_tokens for r in self.reports)

    @property
    def output_tokens(self) -> int:
        return sum(r.output_tokens for r in self.reports)

    @property
    def cost_usd(self) -> Decimal:
        return sum((r.cost_usd for r in self.reports), Decimal(0))

    def invoice_accuracies(self) -> list[float]:
        return [r.summary.invoice_accuracy for r in self.reports]

    def field_accuracies(self) -> list[float]:
        return [r.summary.overall_field_accuracy for r in self.reports]

    def refusal_accuracies(self) -> list[float]:
        return [
            r.summary.refusal_accuracy
            for r in self.reports
            if r.summary.refusal_accuracy is not None
        ]

    def case_pass_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for report in self.reports:
            for score in report.scores:
                counts[score.case_id] = counts.get(score.case_id, 0) + score.correct
        return counts

    def retry_counts(self) -> dict[str, int]:
        """Runs in which an extraction case needed more than one model call.

        A retry that ends well still counts as a pass, so without this the
        headline accuracy would hide first-attempt failures. Refusal cases are
        excluded: they always use every attempt.
        """
        counts: dict[str, int] = {}
        for report in self.reports:
            for score in report.scores:
                if not score.expects_refusal:
                    retried = score.attempts > 1
                    counts[score.case_id] = counts.get(score.case_id, 0) + retried
        return counts

    def wrong_values(self) -> dict[str, Counter[tuple[str, str, str]]]:
        """case id -> Counter of (field, expected, got) over all runs."""
        seen: dict[str, Counter[tuple[str, str, str]]] = {}
        for report in self.reports:
            for score in report.scores:
                for name, (expected, got) in score.mismatches.items():
                    seen.setdefault(score.case_id, Counter())[(name, expected, got)] += 1
        return seen

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "runs": [r.to_dict() for r in self.reports],
            "case_pass_counts": self.case_pass_counts(),
            "cost_usd": str(self.cost_usd),
        }


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


async def run_eval_repeated(
    extractor: Extractor, runs: int, cases: tuple[EvalCase, ...] = CASES
) -> RepeatedReport:
    if runs < 1:
        raise ValueError("runs must be at least 1")
    # One run after the other: the eval measures the model, not its rate limits.
    return RepeatedReport([await run_eval(extractor, cases) for _ in range(runs)])


def _range(values: list[float]) -> str:
    return f"mean {mean(values):.1%}  (min {min(values):.1%}, max {max(values):.1%})"


def format_repeated(report: RepeatedReport) -> str:
    wrong = report.wrong_values()
    retries = report.retry_counts()
    lines = [
        f"Model: {report.model}   Runs: {report.runs}",
        "",
        f"{'case':<36} passed",
    ]
    for case_id, passed in report.case_pass_counts().items():
        marker = "" if passed == report.runs else "   <-- not stable"
        if retries.get(case_id):
            marker += f"   (needed a retry in {retries[case_id]}/{report.runs} runs)"
        lines.append(f"{case_id:<36} {passed}/{report.runs}{marker}")
        for (name, expected, got), times in wrong.get(case_id, Counter()).most_common():
            lines.append(f"    {name}: expected {expected!r}, got {got!r}  ({times}x)")

    lines += [
        "",
        f"Invoices fully correct: {_range(report.invoice_accuracies())}",
        f"All fields:             {_range(report.field_accuracies())}",
    ]
    if refusals := report.refusal_accuracies():
        lines.append(f"Refusals correct:       {_range(refusals)}")
    lines.append(
        f"Tokens: {report.input_tokens} in / {report.output_tokens} out   "
        f"Estimated cost: ${report.cost_usd}"
    )
    return "\n".join(lines)


def save_report(report: EvalReport | RepeatedReport, path: Path = RESULTS_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate invoice extraction.")
    parser.add_argument(
        "--runs", type=int, default=1, help="repeat the eval to measure consistency"
    )
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    asyncio.run(_run(args.runs))


async def _run(runs: int) -> None:
    from invoice_api.services.extraction import (
        ExtractionNotConfigured,
        close_client,
        get_extractor,
    )

    try:
        extractor = await get_extractor()
    except ExtractionNotConfigured:
        raise SystemExit("Set ANTHROPIC_API_KEY in .env to run the eval.") from None

    try:
        if runs == 1:
            report = await run_eval(extractor)
            print(format_report(report))
            print(f"\nSaved to {save_report(report)}")
        else:
            repeated = await run_eval_repeated(extractor, runs)
            print(format_repeated(repeated))
            print(f"\nSaved to {save_report(repeated)}")
    finally:
        await close_client()


if __name__ == "__main__":
    main()
