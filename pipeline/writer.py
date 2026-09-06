"""Bounded, failure-isolating write batches shared by high-volume paths."""
from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from typing import Generic, TypeVar

from pipeline import telemetry

T = TypeVar("T")


class BatchWriter(Generic[T]):
    """Buffer rows and commit durable checkpoints with each bounded batch.

    ``write_batch`` owns the SQL shape and receives a sequence, allowing a
    caller to use ``executemany`` or a PostgreSQL COPY path without the writer
    knowing the table. A failing batch is recursively subdivided so one bad
    source row does not discard otherwise valid work. The irreducible failure
    is reported through ``on_row_error`` and the good rows remain committed.
    """

    def __init__(self, conn, write_batch: Callable[[Sequence[T]], None], *,
                 checkpoint: Callable[[], None] | None = None,
                 on_row_error: Callable[[T, BaseException], None] | None = None,
                 max_rows: int = 1000, max_seconds: float = 5.0,
                 clock: Callable[[], float] = time.monotonic,
                 isolate_failures: bool = True, commit: bool = True,
                 label: str | None = None):
        if max_rows < 1 or max_seconds <= 0:
            raise ValueError("max_rows must be positive and max_seconds must be positive")
        self.conn = conn
        self.write_batch = write_batch
        self.checkpoint = checkpoint
        self.on_row_error = on_row_error
        self.max_rows = max_rows
        self.max_seconds = max_seconds
        self._clock = clock
        self.isolate_failures = isolate_failures
        self.commit = commit
        # A table/purpose name for telemetry only (performance.md:632) --
        # optional and cosmetic, never parsed, so every existing caller that
        # does not pass it keeps working unchanged and just reports under
        # "batch" instead of its own name.
        self.label = label or "batch"
        self._pending: list[T] = []
        self._opened_at: float | None = None
        self.rows_written = 0
        self.rows_failed = 0
        self.batches = 0
        self._savepoint = 0

    def write(self, row: T) -> None:
        if not self._pending:
            self._opened_at = self._clock()
        self._pending.append(row)
        if len(self._pending) >= self.max_rows or self._expired():
            self.flush()

    def write_many(self, rows: Iterable[T]) -> None:
        for row in rows:
            self.write(row)

    def _expired(self) -> bool:
        return (self._opened_at is not None and
                self._clock() - self._opened_at >= self.max_seconds)

    def flush(self) -> int:
        """Write, checkpoint, and commit the pending rows.

        The pending buffer is cleared only after commit. A normal failure is
        rolled back and retried as smaller batches; an irreducible row is
        recorded and skipped so the caller can continue while retaining the
        failure attribution.
        """
        if not self._pending:
            return 0
        batch = self._pending
        written = 0
        started = self._clock()
        # Database batch rows/duration (performance.md:632), matching the
        # shape `pipeline/graph/store.py`'s `graph.store_unwind_batch` log
        # line already reports for Neo4j `UNWIND` batches -- rows and elapsed
        # time, here as a span and a metric rather than a second structlog
        # line, since this class is a low-level primitive shared by many
        # callers (cache writes, m01's procurement channels, embeddings) and
        # adding a log line here would multiply log volume at every one of
        # them rather than at the one place that already made that call.
        # Bytes-per-batch, which the graph line also reports, is deliberately
        # not attempted here: graph rows are already plain dicts bound for
        # JSON; a `BatchWriter` row can be anything `write_batch` accepts
        # (a tuple, a dataclass, a database row), and serializing an
        # arbitrary one just to estimate its size would risk costing more --
        # and failing in more ways -- than the write it is describing.
        with telemetry.span("db.batch_write", table=self.label, rows=len(batch)) as batch_span:
            try:
                if self.isolate_failures:
                    written = self._write_isolated(batch)
                else:
                    self.write_batch(batch)
                    written = len(batch)
                if self.checkpoint is not None:
                    self.checkpoint()
                if self.commit:
                    self.conn.commit()
            except BaseException:
                self.conn.rollback()
                telemetry.counter(
                    "db.batch_write.failures",
                    description="Batches that failed outright (not a single isolated bad row).").add(
                    1, {"table": self.label})
                raise
            finally:
                telemetry.histogram(
                    "db.batch_write.duration_seconds", unit="s",
                    description="Wall time to write, checkpoint and commit one batch.").record(
                    self._clock() - started, {"table": self.label})
            batch_span.set_attribute("written", written)
            if self.rows_failed:
                batch_span.set_attribute("rows_failed_total", self.rows_failed)
        telemetry.histogram(
            "db.batch_write.rows", unit="rows",
            description="Rows written per batch.").record(written, {"table": self.label})
        self._pending = []
        self._opened_at = None
        self.rows_written += written
        self.batches += 1
        return written

    def _write_isolated(self, rows: Sequence[T]) -> int:
        self._savepoint += 1
        savepoint = f"batch_writer_{self._savepoint}"
        self.conn.execute(f"SAVEPOINT {savepoint}")
        try:
            self.write_batch(rows)
            self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            return len(rows)
        except BaseException as exc:
            # Roll back only this attempt. A successful sibling may already
            # have written rows in the surrounding transaction and must not be
            # lost while the failed branch is subdivided.
            self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            if len(rows) == 1:
                self.rows_failed += 1
                telemetry.counter(
                    "db.batch_write.row_failures",
                    description="Rows a batch subdivision could not write, isolated to one row.").add(
                    1, {"table": self.label})
                if self.on_row_error is not None:
                    self.on_row_error(rows[0], exc)
                return 0
            midpoint = len(rows) // 2
            # Each recursive branch is kept in the same eventual transaction;
            # a bad right branch rolls back only its own attempted statements.
            return (self._write_isolated(rows[:midpoint]) +
                    self._write_isolated(rows[midpoint:]))

    def close(self) -> None:
        """Flush at clean shutdown; safe to call repeatedly."""
        self.flush()

    def __enter__(self) -> "BatchWriter[T]":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if exc_type is None:
            self.flush()
        else:
            self._pending.clear()
            self.conn.rollback()
        return False
