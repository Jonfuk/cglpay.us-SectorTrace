"""`pipeline/telemetry.py`'s own contract: a no-op unless explicitly enabled
and the SDK is installed, and a real tracer/meter otherwise.

Marked serial like `tests/test_meters.py` -- this module's `_state` dict is
process-global, exactly like `pipeline.meters`'s NETWORK/DISK, and every test
here mutates it (`configure_telemetry`/`shutdown_telemetry`). Nothing here
touches the database, so this is not about xdist worker isolation the way the
`settings`/`conn` fixtures are; it is about not letting two of *these* tests
race each other's global state within one worker process.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from pipeline import telemetry

pytestmark = pytest.mark.serial


def _settings(**overrides):
    base = {"otel_enabled": False, "otel_exporter_endpoint": None,
            "otel_service_name": "test-service"}
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _reset_telemetry():
    """However a test leaves it, the next one starts from the no-op state --
    the same guarantee `configure_telemetry` itself gives production callers
    that reconfigure mid-process."""
    telemetry.shutdown_telemetry()
    yield
    telemetry.shutdown_telemetry()


def test_disabled_settings_leave_every_call_a_no_op():
    configured = telemetry.configure_telemetry(_settings(otel_enabled=False))
    assert configured is False
    assert telemetry.is_enabled() is False

    with telemetry.span("some.operation", a=1) as span:
        span.set_attribute("b", 2)  # must not raise
    telemetry.counter("some.counter").add(1)
    telemetry.histogram("some.histogram").record(1.5)
    with telemetry.timed_histogram("some.timed"):
        pass


def test_never_configured_is_the_same_no_op_path():
    """A caller that never calls `configure_telemetry` at all -- most of the
    offline test suite -- gets the identical no-op behaviour, not an
    AttributeError on an uninitialised tracer."""
    assert telemetry.is_enabled() is False
    with telemetry.span("x") as span:
        span.record_exception(RuntimeError("boom"))
        span.set_status("ERROR")


def test_missing_sdk_degrades_to_the_no_op_path(monkeypatch):
    """Simulates a checkout without `uv sync --extra otel`: importing the SDK
    inside `configure_telemetry` raises, and that must be caught, not
    propagated -- a pipeline must run with no telemetry, not fail to start."""
    import sys

    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", None)
    configured = telemetry.configure_telemetry(_settings(otel_enabled=True))
    assert configured is False
    assert telemetry.is_enabled() is False
    with telemetry.span("x"):
        pass  # must not raise


def test_enabled_records_real_spans_with_attributes():
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    configured = telemetry.configure_telemetry(
        _settings(otel_enabled=True), span_exporter=exporter,
        metric_reader=InMemoryMetricReader())
    assert configured is True
    assert telemetry.is_enabled() is True

    with telemetry.span("pipeline.run", run_id="abc123", modules_total=3, absent=None) as run_span:
        run_span.set_attribute("modules_completed", 3)

    finished = exporter.get_finished_spans()
    assert len(finished) == 1
    assert finished[0].name == "pipeline.run"
    attributes = dict(finished[0].attributes)
    assert attributes["run_id"] == "abc123"
    assert attributes["modules_total"] == 3
    assert attributes["modules_completed"] == 3
    # A None-valued attribute is dropped rather than sent as null -- see
    # `span()`'s docstring for why.
    assert "absent" not in attributes


def test_a_span_records_the_exception_that_escaped_it():
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    telemetry.configure_telemetry(_settings(otel_enabled=True), span_exporter=exporter)

    with pytest.raises(RuntimeError):
        with telemetry.span("archive.put", backend="filesystem"):
            raise RuntimeError("disk full")

    finished = exporter.get_finished_spans()
    assert len(finished) == 1
    assert finished[0].status.status_code.name == "ERROR"


def test_counters_and_histograms_accumulate_and_are_cached_by_name():
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    reader = InMemoryMetricReader()
    telemetry.configure_telemetry(_settings(otel_enabled=True), metric_reader=reader)

    first = telemetry.counter("db.batch_write.rows_test")
    second = telemetry.counter("db.batch_write.rows_test")
    assert first is second  # created once, per OpenTelemetry's own instrument contract

    telemetry.counter("test.hits").add(1, {"table": "widgets"})
    telemetry.counter("test.hits").add(2, {"table": "widgets"})
    telemetry.histogram("test.duration").record(0.5)

    data = reader.get_metrics_data()
    metric_names = {
        metric.name
        for resource_metrics in data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
    }
    assert {"test.hits", "test.duration"} <= metric_names


def test_shutdown_is_idempotent_and_reverts_to_no_op():
    telemetry.configure_telemetry(_settings(otel_enabled=True))
    assert telemetry.is_enabled() is True
    telemetry.shutdown_telemetry()
    telemetry.shutdown_telemetry()
    assert telemetry.is_enabled() is False
    with telemetry.span("x"):
        pass  # must not raise


def test_reconfiguring_does_not_leak_the_previous_exporter():
    """A second `configure_telemetry` call must start clean -- registering
    against OpenTelemetry's *global* tracer provider instead would make a
    second call in the same process permanently stuck with the first
    exporter, which would break exactly the test-isolation this module
    exists to support."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    first_exporter = InMemorySpanExporter()
    telemetry.configure_telemetry(_settings(otel_enabled=True), span_exporter=first_exporter)
    with telemetry.span("first.span"):
        pass
    assert len(first_exporter.get_finished_spans()) == 1

    second_exporter = InMemorySpanExporter()
    telemetry.configure_telemetry(_settings(otel_enabled=True), span_exporter=second_exporter)
    with telemetry.span("second.span"):
        pass
    assert len(second_exporter.get_finished_spans()) == 1
    # The first exporter never saw the second span -- proof the providers
    # were replaced, not layered.
    assert len(first_exporter.get_finished_spans()) == 1
