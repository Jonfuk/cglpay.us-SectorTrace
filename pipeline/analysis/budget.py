"""Cooperative batch cancellation and bounded model-call accounting."""
from __future__ import annotations

from dataclasses import dataclass


class AnalysisCancelled(RuntimeError):
    """Raised between batches after an operator cancellation request."""


class CostCeilingExceeded(RuntimeError):
    """Raised before a model call would exceed the release ceiling."""


@dataclass
class CallBudget:
    ceiling_micros: int = 0
    spent_micros: int = 0
    calls: int = 0
    cache_hits: int = 0
    cancelled: bool = False

    def before_call(self, estimated_micros: int = 0) -> None:
        if self.cancelled:
            raise AnalysisCancelled("analysis run cancelled at a batch boundary")
        if self.ceiling_micros > 0 and self.spent_micros + estimated_micros > self.ceiling_micros:
            raise CostCeilingExceeded("analysis cost ceiling reached before the next model call")

    def record(self, cost_micros: int = 0, *, cached: bool = False) -> None:
        self.spent_micros += max(0, int(cost_micros or 0))
        self.calls += 1
        if cached:
            self.cache_hits += 1

    def cancel(self) -> None:
        self.cancelled = True


def run_batches(items, worker, *, batch_size: int = 100, budget: CallBudget | None = None) -> dict:
    """Run work only at batch boundaries so cancellation never loses a partial batch."""
    budget = budget or CallBudget()
    completed = 0
    results = []
    values = list(items)
    for start in range(0, len(values), max(1, batch_size)):
        budget.before_call()
        batch = values[start:start + max(1, batch_size)]
        results.extend(worker(batch))
        completed += len(batch)
        if budget.cancelled:
            break
    return {"completed": completed, "total": len(values), "results": results,
            "cancelled": budget.cancelled, "spent_micros": budget.spent_micros,
            "cache_hits": budget.cache_hits}
