"""QuaPy-style document-level prevalence diagnostics for narrative corpora."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from pipeline.analysis.signals import utcnow


@dataclass(frozen=True)
class PrevalenceResult:
    pacc: float | None
    emq: float | None
    positives: int
    negatives: int
    subjects: int
    continue_exploration: bool
    suppressed: bool
    reason: str | None = None


def diagnostics(*, positives: int, negatives: int, subjects: int, pacc: float | None,
                emq: float | None, min_examples: int = 50, min_subjects: int = 10) -> PrevalenceResult:
    suppressed = positives < min_examples or negatives < min_examples or subjects < min_subjects
    if suppressed:
        return PrevalenceResult(pacc, emq, positives, negatives, subjects, False, True,
                                "requires 50 positives, 50 negatives and 10 subjects")
    residual = any(value is not None and value >= .01 for value in (pacc, emq))
    disagreement = pacc is not None and emq is not None and abs(pacc - emq) > .02
    return PrevalenceResult(pacc, emq, positives, negatives, subjects,
                            residual or disagreement, False,
                            "residual prevalence or estimator disagreement" if residual or disagreement else None)


def save_diagnostics(conn, *, release_id: str, domain_id: str,
                     result: PrevalenceResult) -> str:
    prevalence_id = f"prevalence-{uuid.uuid4()}"
    conn.execute(
        "INSERT INTO analysis_prevalence_diagnostics (prevalence_id, release_id, domain_id, positives, "
        "negatives, subjects, pacc, emq, continue_exploration, suppressed, reason, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (prevalence_id, release_id, domain_id, result.positives, result.negatives, result.subjects,
         result.pacc, result.emq, int(result.continue_exploration), int(result.suppressed),
         result.reason, utcnow()))
    return prevalence_id
