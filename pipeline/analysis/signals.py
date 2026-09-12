"""Common envelope for deterministic and model-derived analysis signals."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

DIRECTIONS = ("adverse", "improving", "neutral", "mixed", "unknown")
ASSERTION_STATUSES = ("affirmed", "negated", "historical", "planned", "hypothetical", "unknown")


class SignalValidationError(ValueError):
    pass


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Signal:
    signal_id: str
    release_id: str
    domain_id: str
    taxonomy_namespace: str
    signal_type: str
    subject_type: str
    subject_id: str
    direction: str
    assertion_status: str
    period_start: str | None
    period_end: str | None
    evidence_refs: tuple[str, ...]
    derivation_method: str
    confidence_contract: dict[str, Any]
    human_verified: bool = False
    created_at: str = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.signal_id or not self.release_id or not self.domain_id:
            raise SignalValidationError("signal_id, release_id and domain_id are required")
        if self.direction not in DIRECTIONS:
            raise SignalValidationError(f"invalid direction {self.direction!r}")
        if self.assertion_status not in ASSERTION_STATUSES:
            raise SignalValidationError(f"invalid assertion status {self.assertion_status!r}")
        if self.human_verified:
            raise SignalValidationError("automated signals cannot be human_verified")
        if not self.evidence_refs:
            raise SignalValidationError("automated signals need provenance references")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"evidence_refs": list(self.evidence_refs)}

    def db_values(self) -> tuple[Any, ...]:
        return (self.signal_id, self.release_id, self.domain_id, self.taxonomy_namespace,
                self.signal_type, self.subject_type, self.subject_id, self.direction,
                self.assertion_status, self.period_start, self.period_end,
                json.dumps(self.evidence_refs), self.derivation_method,
                json.dumps(self.confidence_contract, sort_keys=True), 0, self.created_at)


def signal_id(release_id: str, domain_id: str, subject_id: str, signal_type: str,
              evidence_refs: list[str] | tuple[str, ...]) -> str:
    stable = "|".join((release_id, domain_id, subject_id, signal_type, *sorted(evidence_refs)))
    return "signal-" + hashlib.sha256(stable.encode()).hexdigest()[:24]


def new_signal(*, release_id: str, domain_id: str, taxonomy_namespace: str,
               signal_type: str, subject_type: str, subject_id: str, direction: str,
               assertion_status: str, period_start: str | None = None,
               period_end: str | None = None, evidence_refs: list[str] | tuple[str, ...],
               derivation_method: str, confidence_contract: dict[str, Any]) -> Signal:
    return Signal(signal_id=signal_id(release_id, domain_id, subject_id, signal_type, evidence_refs),
                  release_id=release_id, domain_id=domain_id, taxonomy_namespace=taxonomy_namespace,
                  signal_type=signal_type, subject_type=subject_type, subject_id=subject_id,
                  direction=direction, assertion_status=assertion_status,
                  period_start=period_start, period_end=period_end,
                  evidence_refs=tuple(evidence_refs), derivation_method=derivation_method,
                  confidence_contract=confidence_contract)
