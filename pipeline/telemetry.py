"""OpenTelemetry traces and metrics (performance.md:632), alongside structlog.

Two different jobs and this module only does one of them. `structlog` (see
`pipeline/logging_conf.py`) is still the human-readable audit record --
`module.finished`, `run.phase`, every fetched URL. What is added here is a
second, machine-consumable view of the same operational facts -- span
durations, counts, byte totals -- for whoever is watching a run through a
tracing backend rather than a log tail. Neither replaces the other; a caller
that adds a span here keeps its existing `log.info(...)` call exactly as it
was.

CONSTRAINT, not a convention: a span attribute or metric label is an
operational identifier -- a module name, a job/run/release/quarantine id, a
row count, a byte count, a duration, a status string -- and nothing else.
Never a source URL's query string, a document's extracted text, a person's
name, or any value a `restricted_` table holds (CLAUDE.md settled decision
3). Those stay out of exports for the same reason they stay out of every
other export this pipeline produces, and a tracing backend is an export: it
is very often a third-party SaaS product, and there is no `guard_columns()`
standing between an attribute and it.

Off by default (`Settings.otel_enabled`, matching `cache_enabled`'s pattern in
`pipeline/web/cache.py`): a checkout and the offline test suite must behave
byte-identically whether or not the optional `otel` extra is even installed.
Every public function below degrades to a documented no-op both when
`configure_telemetry` was never called (or was called with telemetry
disabled) and when the SDK is not importable -- so a call site never needs an
`if settings.otel_enabled:` guard of its own. The OpenTelemetry import lives
inside `configure_telemetry`, not at this module's top level, so importing
`pipeline.telemetry` itself never requires the extra to be installed; every
other function only ever touches the small amount of state that function
sets, never the `opentelemetry` package directly.
"""
from __future__ import annotations

import contextlib
import time
from typing import Any, Iterator

import structlog

log = structlog.get_logger()


class _NullSpan:
    """The span a caller gets when telemetry is off or the SDK is absent.

    Every method is a no-op returning None, so `span.set_attribute(...)` reads
    identically at every call site regardless of whether a real span is
    underneath -- the point of this class, not an oversight.
    """

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_attributes(self, attributes: dict) -> None:
        pass

    def record_exception(self, exc: BaseException) -> None:
        pass

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        pass

    def end(self) -> None:
        pass


class _NullInstrument:
    """Stands in for a counter or histogram. `.add`/`.record` share one
    no-op shape, so one class covers both instrument kinds."""

    def add(self, amount: Any, attributes: dict | None = None) -> None:
        pass

    def record(self, amount: Any, attributes: dict | None = None) -> None:
        pass


_NULL_SPAN = _NullSpan()
_NULL_INSTRUMENT = _NullInstrument()

# Mutable module state rather than a class instance: every call site imports
# this module and calls its functions directly (`telemetry.span(...)`,
# `telemetry.counter(...)`), the same shape `pipeline.meters`'s module-level
# NETWORK/DISK meters already use here, so a second caller never needs to
# thread a `Telemetry` object through function signatures it does not
# otherwise need to change. `_state["tracer"]`/`_state["meter"]` are real SDK
# objects once `configure_telemetry` succeeds, and stay None otherwise -- the
# single fact every function below branches on.
_state: dict[str, Any] = {"tracer": None, "meter": None, "instruments": {},
                          "providers": None}


def is_enabled() -> bool:
    """Whether a real tracer/meter is configured. Call sites do not need this
    -- `span()`/`counter()`/`histogram()` already degrade safely -- but a test
    asserting the no-op path chose correctly does."""
    return _state["tracer"] is not None


def configure_telemetry(settings: Any, *, span_exporter: Any = None,
                        metric_reader: Any = None) -> bool:
    """Set up (or tear down) this process's tracer/meter, from `Settings`.

    Idempotent and safe to call more than once -- a fresh call always starts
    from a clean provider rather than layering a second one over the first,
    which matters for tests that reconfigure between cases (this module keeps
    its own `TracerProvider`/`MeterProvider` instances rather than registering
    them as the OpenTelemetry *global* provider, precisely so a second
    `configure_telemetry` call in the same process is not stuck with the
    first call's exporter -- the global-provider API only ever accepts the
    first registration).

    Returns True when a real tracer/meter is now active, False when this
    process is (still) running the no-op path -- disabled by
    `settings.otel_enabled`, or the `otel` extra is not installed.

    `span_exporter`/`metric_reader` let a test substitute an in-memory
    exporter without needing a real collector; production callers never pass
    these; the default is built from `settings` (see `_default_span_exporter`
    / `_default_metric_reader` below).
    """
    _shutdown_providers()
    if not getattr(settings, "otel_enabled", False):
        return False
    try:
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    except ImportError:
        # A checkout that turned OTEL_ENABLED on without `uv sync --extra
        # otel` gets a working pipeline with no telemetry, not an import
        # error partway through a run -- the same shape `GraphStore.connect`
        # gives a checkout missing the `graph` extra.
        log.warning("telemetry.otel_not_installed")
        return False

    resource = Resource.create({
        "service.name": getattr(settings, "otel_service_name", None) or "sectortrace-pipeline",
    })

    tracer_provider = TracerProvider(resource=resource)
    # `SimpleSpanProcessor` exports synchronously on every span end rather
    # than batching on a background thread. Deliberate here, not a shortcut:
    # this pipeline's spans are coarse (one per run, per module, per batch,
    # per model call -- not one per HTTP request), so the export cost is
    # negligible next to the work each span wraps, and a synchronous exporter
    # is what makes the in-memory exporter tests below deterministic without
    # a manual flush call, and what guarantees a short-lived CLI command's
    # spans are actually sent before the process exits.
    tracer_provider.add_span_processor(
        SimpleSpanProcessor(span_exporter or _default_span_exporter(settings)))

    meter_provider = MeterProvider(
        resource=resource, metric_readers=[metric_reader or _default_metric_reader(settings)])

    _state["tracer"] = tracer_provider.get_tracer("sectortrace.pipeline")
    _state["meter"] = meter_provider.get_meter("sectortrace.pipeline")
    _state["instruments"] = {}
    _state["providers"] = (tracer_provider, meter_provider)
    log.info("telemetry.configured",
             exporter="otlp" if getattr(settings, "otel_exporter_endpoint", None) else "console")
    return True


def _default_span_exporter(settings: Any) -> Any:
    """An OTLP exporter when an endpoint is configured; otherwise a console
    exporter -- inert by construction (stdout, never a socket), so
    `OTEL_ENABLED=true` alone can never be the reason a process tries to
    reach a collector that is not there. Nothing in CI or the offline suite
    sets `otel_enabled`, so this path is never exercised by the default test
    run regardless."""
    endpoint = getattr(settings, "otel_exporter_endpoint", None)
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        return OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter
    return ConsoleSpanExporter()


def _default_metric_reader(settings: Any) -> Any:
    """The metrics counterpart of `_default_span_exporter`. A `Periodic
    ExportingMetricReader` either way -- console or OTLP, both are push
    exporters under this reader -- so metrics leave the process on the same
    schedule regardless of destination."""
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    endpoint = getattr(settings, "otel_exporter_endpoint", None)
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        exporter = OTLPMetricExporter(endpoint=f"{endpoint.rstrip('/')}/v1/metrics")
    else:
        from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
        exporter = ConsoleMetricExporter()
    return PeriodicExportingMetricReader(exporter, export_interval_millis=60_000)


def shutdown_telemetry() -> None:
    """Flush and release whatever `configure_telemetry` set up, and revert to
    the no-op path. Idempotent. Tests call this in teardown so a
    `PeriodicExportingMetricReader`'s background export thread never outlives
    the test that created it; a real process calling `configure_telemetry`
    normally runs until it exits and never needs to call this itself."""
    _shutdown_providers()


def _shutdown_providers() -> None:
    providers = _state.get("providers")
    _state["tracer"] = None
    _state["meter"] = None
    _state["instruments"] = {}
    _state["providers"] = None
    if providers is None:
        return
    for provider in providers:
        try:
            provider.shutdown()
        except Exception as exc:  # pragma: no cover - best-effort teardown
            log.warning("telemetry.shutdown_failed", error=str(exc))


@contextlib.contextmanager
def span(name: str, **attributes: Any) -> Iterator[Any]:
    """A span for the duration of the `with` block. Falls back to
    `_NULL_SPAN` when telemetry is off, so every call site reads the same
    whether or not anything is recording.

    `None`-valued attributes are dropped rather than sent as `None` --
    OpenTelemetry attribute values must be a bool/int/float/str (or a
    homogeneous sequence of one of those), and a caller here very often has
    an optional identifier (a `release_id` that only exists for an analysis
    run, a `job_id` only a worker-executed run has) that is genuinely absent
    rather than a value worth recording as null.
    """
    tracer = _state["tracer"]
    if tracer is None:
        yield _NULL_SPAN
        return
    clean = {key: value for key, value in attributes.items() if value is not None}
    with tracer.start_as_current_span(name) as current:
        if clean:
            current.set_attributes(clean)
        yield current


def start_span(name: str, **attributes: Any) -> Any:
    """A span a caller ends itself (`.end()`), for a lifetime that does not
    nest inside one `with` block -- see `PipelineWorker._claim_and_run`,
    where the span outlives a `try/finally` around a heartbeat thread rather
    than one contiguous block. Prefer `span()` above wherever the lifetime
    fits a `with`."""
    tracer = _state["tracer"]
    if tracer is None:
        return _NULL_SPAN
    clean = {key: value for key, value in attributes.items() if value is not None}
    current = tracer.start_span(name)
    if clean:
        current.set_attributes(clean)
    return current


def counter(name: str, *, unit: str = "1", description: str = "") -> Any:
    """A monotonic counter, created once per name and cached -- OpenTelemetry
    instruments are meant to be created once and reused, not once per call."""
    return _instrument("counter", name, unit=unit, description=description)


def histogram(name: str, *, unit: str = "s", description: str = "") -> Any:
    """A distribution (durations, byte counts, row counts). Same caching
    rule as `counter` above."""
    return _instrument("histogram", name, unit=unit, description=description)


def _instrument(kind: str, name: str, *, unit: str, description: str) -> Any:
    meter = _state["meter"]
    if meter is None:
        return _NULL_INSTRUMENT
    key = (kind, name)
    cached = _state["instruments"].get(key)
    if cached is not None:
        return cached
    factory = meter.create_counter if kind == "counter" else meter.create_histogram
    instrument = factory(name, unit=unit, description=description)
    _state["instruments"][key] = instrument
    return instrument


@contextlib.contextmanager
def timed_histogram(name: str, *, unit: str = "s", description: str = "",
                     attributes: dict | None = None) -> Iterator[None]:
    """Record how long the `with` block took, into `histogram(name)`. For the
    common case of "time this operation"; a caller that already has its own
    duration (e.g. `execute_module`'s `row["elapsed"]`) should record that
    number directly with `histogram(name).record(...)` instead of timing it
    twice."""
    started = time.monotonic()
    try:
        yield
    finally:
        histogram(name, unit=unit, description=description).record(
            time.monotonic() - started, attributes or {})
