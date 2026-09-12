"""Release promotion metrics shared by DSPy challengers and verifiers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProgramMetrics:
    proxy_score: float
    quote_recoverability: float
    critical_mutation_failures: int
    agreement_score: float


def promotion_eligible(candidate: ProgramMetrics, baseline: ProgramMetrics) -> bool:
    return (candidate.proxy_score >= baseline.proxy_score + .05 and
            candidate.quote_recoverability >= 1.0 and
            candidate.critical_mutation_failures == 0 and
            candidate.agreement_score >= baseline.agreement_score - .02)


def compare_programs(conn, *, candidate: ProgramMetrics, baseline: ProgramMetrics,
                     program_version_id: str, release_id: str, domain_id: str,
                     model_id: str, config: dict) -> str:
    import hashlib
    import json

    from pipeline.analysis.signals import utcnow

    status = "champion" if promotion_eligible(candidate, baseline) else "challenger"
    conn.execute(
        "INSERT INTO analysis_program_versions (program_version_id, release_id, domain_id, model_id, "
        "program_kind, status, proxy_score, quote_recoverability, mutation_failure_count, agreement_score, "
        "config_json, created_at) VALUES (%s, %s, %s, %s, 'dspy', %s, %s, %s, %s, %s, %s, %s)",
        (program_version_id, release_id, domain_id, model_id, status, candidate.proxy_score,
         candidate.quote_recoverability, candidate.critical_mutation_failures,
         candidate.agreement_score, json.dumps({**config, "config_sha256": hashlib.sha256(
             json.dumps(config, sort_keys=True).encode()).hexdigest()}, sort_keys=True), utcnow()))
    return status
