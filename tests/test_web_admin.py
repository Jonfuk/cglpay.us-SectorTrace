"""Running the pipeline from a browser.

This is the first thing in the web layer that reaches the outside world: every
other route reads the warehouse or records a judgement about it, and this one
starts a crawl. The tests that matter are therefore about what it refuses --
a second concurrent run, a limit of zero, an unparseable date, an unknown
module -- and about the run it does start being the same run the CLI would
have started, rather than a second implementation that drifts.
"""
from __future__ import annotations

import json
import logging
import threading
import time

import httpx
import pytest

from pipeline import runner
from pipeline.registry import MODULE_REGISTRY, resolve_run_order, resolve_run_waves
from pipeline.web import admin
from pipeline.web.jobs import Job, JobError, JobRegistry
from pipeline.web.server import build_server


@pytest.fixture
def configured_logging(settings, monkeypatch):
    """What `pipeline web` does before it serves.

    The job log is captured off the root logger, which only sees anything
    because `configure_logging` points structlog at stdlib logging. That is a
    process-global setup step performed by the CLI, so a test that skipped it
    would exercise a capture path that can never fire and pass while the real
    one was broken. The real function is called, with its settings redirected
    into tmp so nothing lands in the repo's logs/.
    """
    from pipeline import logging_conf

    monkeypatch.setattr(logging_conf, "get_settings", lambda: settings)
    logging_conf.configure_logging("test-web-admin")
    yield
    logging.getLogger().handlers.clear()


@pytest.fixture
def client(conn, settings, configured_logging):
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def post(client, path, body):
    return client.post(path, json=body)


def wait_for(predicate, timeout=10.0):
    """Poll until true. Jobs are threads; the alternative is a sleep long
    enough to be slow and short enough to be flaky."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def fake_module(monkeypatch):
    """A registered module that writes one row and says what it is doing."""
    ran = []

    def module(ctx):
        ctx.phase("counting things")
        for _ in ctx.track([1, 2, 3], "rows"):
            pass
        ctx.conn.execute(
            "INSERT INTO module_cursors (module, cursor_value, updated_at) "
            "VALUES ('a_fake', '2026-01-01', '2026-01-01T00:00:00Z')")
        ran.append(True)

    monkeypatch.setitem(MODULE_REGISTRY, "a_fake", module)
    return ran


# --- the module inventory ------------------------------------------------------


def test_modules_lists_what_can_be_run(client, fake_module):
    payload = client.get("/api/admin/modules").json()
    names = {m["name"] for m in payload["modules"]}

    assert "a_fake" in names
    assert "m00_geography" in names, "the real registry should be discovered too"

    geography = next(m for m in payload["modules"] if m["name"] == "m00_geography")
    assert geography["wave"] == 1, "a module with no dependencies runs in wave 1"
    assert geography["pending_review"] == 0
    assert geography["cursor_value"] is None


def test_modules_reports_dependencies_and_since_support(client):
    payload = client.get("/api/admin/modules").json()
    by_name = {m["name"]: m for m in payload["modules"]}

    dependent = [m for m in payload["modules"] if m["depends_on"]]
    assert dependent, "expected at least one module to declare a dependency"
    for module in dependent:
        assert module["wave"] > 1, f"{module['name']} depends on something but runs first"
        for dependency in module["depends_on"]:
            assert by_name[dependency]["wave"] < module["wave"]

    assert any(m["supports_since"] for m in payload["modules"])


def test_modules_counts_the_queue_it_would_add_to(client, conn):
    from pipeline import db

    db.record_review_item(conn, "m01_procurement", "unmatched_buyer_name", "Ambridge BC")
    db.record_parse_failure(conn, "m01_procurement", "value", "£x", "not a number")
    conn.commit()

    payload = client.get("/api/admin/modules").json()
    procurement = next(m for m in payload["modules"] if m["name"] == "m01_procurement")
    assert procurement["pending_review"] == 1
    assert procurement["parse_failures"] == 1


# --- planning agrees with the CLI ----------------------------------------------


def test_planning_all_resolves_the_same_waves_as_the_cli():
    """The one piece deliberately not shared with cli.run, because the CLI's
    version is interleaved with what it prints. Held together here instead."""
    admin.registry()
    planned = admin.plan("all", since=None, limit=None)

    assert planned["targets"] == list(resolve_run_order())
    assert planned["waves"] == resolve_run_waves(resolve_run_order())


def test_planning_one_module_still_resolves_its_wave(fake_module):
    planned = admin.plan("a_fake", since=None, limit=None)
    assert planned["targets"] == ["a_fake"]
    assert planned["waves"] == [["a_fake"]]


def test_planning_reports_what_since_will_not_affect():
    admin.registry()
    planned = admin.plan("m00_geography", since="2026-01-01", limit=None)
    # m00 does not filter by date; saying so is the CLI's stderr warning.
    assert planned["since_ignored_by"] == ["m00_geography"]


# --- refusals -------------------------------------------------------------------


def test_an_unknown_module_is_a_404_not_a_run(client):
    response = post(client, "/api/admin/run", {"module": "m99_invented"})
    assert response.status_code == 404
    assert "m99_invented" in response.json()["error"]


def test_a_limit_of_zero_is_refused_rather_than_reinterpreted(client, fake_module):
    """Every module tests `if ctx.limit:`, so zero reads as "no limit at all".
    Accepting it would turn "fetch nothing" into a full live crawl."""
    response = post(client, "/api/admin/run", {"module": "a_fake", "limit": 0})
    assert response.status_code == 400
    assert "1 or more" in response.json()["error"]
    assert not fake_module, "the module ran despite the refusal"


def test_an_unparseable_since_is_refused_before_anything_fetches(client, fake_module):
    response = post(client, "/api/admin/run",
                     {"module": "a_fake", "since": "last tuesday"})
    assert response.status_code == 400
    assert "ISO date" in response.json()["error"]
    assert not fake_module


def test_a_run_needs_a_module(client):
    assert post(client, "/api/admin/run", {}).status_code == 400


def test_starting_a_run_needs_a_json_content_type(client, fake_module):
    """The CSRF guard that covers every other write covers this one too --
    which matters more here, because this write starts a crawl."""
    response = client.post("/api/admin/run", content=json.dumps({"module": "a_fake"}),
                            headers={"Content-Type": "text/plain"})
    assert response.status_code == 415
    assert not fake_module


def test_a_run_from_another_origin_is_refused(client, fake_module):
    response = client.post("/api/admin/run", json={"module": "a_fake"},
                            headers={"Origin": "http://evil.example"})
    assert response.status_code == 403
    assert not fake_module


def test_a_run_cannot_be_started_by_a_get(client, fake_module):
    assert client.get("/api/admin/run").status_code == 404
    assert not fake_module


# --- running --------------------------------------------------------------------


def test_a_run_executes_the_module_and_reports_what_it_did(client, fake_module, conn):
    started = post(client, "/api/admin/run", {"module": "a_fake"})
    assert started.status_code == 200
    job_id = started.json()["id"]
    assert started.json()["state"] == "running"

    assert wait_for(lambda: client.get(f"/api/admin/jobs/{job_id}").json()["state"]
                     != "running"), "the job never finished"

    finished = client.get(f"/api/admin/jobs/{job_id}").json()
    assert finished["state"] == "finished"
    assert finished["error"] is None
    assert [row["module"] for row in finished["summary"]] == ["a_fake"]
    assert finished["summary"][0]["status"] == "ok"
    assert fake_module, "the module did not actually run"

    # And it wrote: a run from the browser is a real run.
    assert conn.execute(
        "SELECT COUNT(*) FROM module_cursors WHERE module = 'a_fake'").fetchone()[0] == 1


def test_a_dry_run_rolls_back_what_it_did(client, fake_module, conn):
    job_id = post(client, "/api/admin/run",
                   {"module": "a_fake", "dry_run": True}).json()["id"]
    assert wait_for(lambda: client.get(f"/api/admin/jobs/{job_id}").json()["state"]
                     != "running")

    assert fake_module, "a dry run still runs the module"
    assert conn.execute(
        "SELECT COUNT(*) FROM module_cursors WHERE module = 'a_fake'").fetchone()[0] == 0


def test_a_failing_module_fails_its_job_without_taking_the_server_down(
        client, monkeypatch):
    def boom(ctx):
        raise RuntimeError("the source moved")

    monkeypatch.setitem(MODULE_REGISTRY, "a_boom", boom)
    job_id = post(client, "/api/admin/run", {"module": "a_boom"}).json()["id"]
    assert wait_for(lambda: client.get(f"/api/admin/jobs/{job_id}").json()["state"]
                     != "running")

    finished = client.get(f"/api/admin/jobs/{job_id}").json()
    # The job completed; the *module* failed, and says so in the summary the
    # same way the CLI's does.
    assert finished["state"] == "finished"
    assert finished["summary"][0]["status"] == "failed"
    assert "the source moved" in finished["summary"][0]["error"]
    assert client.get("/api/overview").status_code == 200, "the server survived"


def test_the_log_carries_what_the_module_reported(client, fake_module):
    job_id = post(client, "/api/admin/run", {"module": "a_fake"}).json()["id"]
    assert wait_for(lambda: client.get(f"/api/admin/jobs/{job_id}").json()["state"]
                     != "running")

    text = " ".join(line["text"] for line
                     in client.get(f"/api/admin/jobs/{job_id}").json()["log"])
    assert "counting things" in text, "ctx.phase() should reach the browser"
    assert "a_fake" in text


def test_the_log_is_delivered_incrementally_by_index(client, fake_module):
    job_id = post(client, "/api/admin/run", {"module": "a_fake"}).json()["id"]
    assert wait_for(lambda: client.get(f"/api/admin/jobs/{job_id}").json()["state"]
                     != "running")

    everything = client.get(f"/api/admin/jobs/{job_id}").json()
    assert everything["log"][0]["i"] == 0

    cut = everything["log"][2]["i"]
    rest = client.get(f"/api/admin/jobs/{job_id}?after={cut}").json()
    assert [line["i"] for line in rest["log"]] == [
        line["i"] for line in everything["log"] if line["i"] > cut]
    assert rest["next"] == everything["log"][-1]["i"]

    # Asking again from the end returns nothing, which is what polling does
    # for most of a long run.
    assert client.get(f"/api/admin/jobs/{job_id}?after={rest['next']}").json()["log"] == []


def test_a_missing_job_is_a_404(client):
    assert client.get("/api/admin/jobs/999").status_code == 404


def test_jobs_lists_them_newest_first(client, fake_module):
    first = post(client, "/api/admin/run", {"module": "a_fake"}).json()["id"]
    assert wait_for(lambda: client.get("/api/admin/jobs").json()["running"] is None)
    second = post(client, "/api/admin/run", {"module": "a_fake"}).json()["id"]
    assert wait_for(lambda: client.get("/api/admin/jobs").json()["running"] is None)

    listed = client.get("/api/admin/jobs").json()
    assert [job["id"] for job in listed["jobs"]][:2] == [second, first]
    # The list view carries no log: it is polled while a run is in progress.
    assert "log" not in listed["jobs"][0]


# --- one at a time --------------------------------------------------------------


def test_a_second_run_is_refused_while_one_is_going(client, monkeypatch):
    """Not queued. The warehouse has one write slot, so a second run would
    wait on the first anyway, and two runs against the same public sources at
    once is what the rate limit exists to prevent."""
    release = threading.Event()

    def slow(ctx):
        release.wait(timeout=10)

    monkeypatch.setitem(MODULE_REGISTRY, "a_slow", slow)
    first = post(client, "/api/admin/run", {"module": "a_slow"}).json()["id"]

    try:
        second = post(client, "/api/admin/run", {"module": "a_slow"})
        assert second.status_code == 409
        # The refusal says which job is in the way, so the page can offer it.
        assert second.json()["job_id"] == first
        assert "already running" in second.json()["error"]
    finally:
        release.set()

    assert wait_for(lambda: client.get("/api/admin/jobs").json()["running"] is None)
    # And the slot is free again afterwards.
    assert post(client, "/api/admin/run", {"module": "a_slow"}).status_code == 200


def test_the_slot_is_claimed_once_even_when_two_requests_arrive_together():
    """The id allocation and the claim happen under one lock, so this cannot
    be won by both callers."""
    registry = JobRegistry()
    release = threading.Event()
    started = []
    refused = []
    barrier = threading.Barrier(4)

    def attempt():
        barrier.wait(timeout=5)
        try:
            started.append(registry.start(
                "run", "x", {}, lambda: release.wait(timeout=5), set()))
        except JobError as exc:
            refused.append(exc)

    threads = [threading.Thread(target=attempt) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    release.set()

    assert len(started) == 1
    assert len(refused) == 3
    assert all(exc.status == 409 for exc in refused)


def test_the_slot_is_released_when_a_job_raises():
    """A strategy failure must not wedge the registry for the process's life."""
    registry = JobRegistry()

    def explode():
        raise RuntimeError("no")

    job = registry.start("run", "x", {}, explode, set())
    assert wait_for(lambda: registry.get(job.id).state == "failed")
    assert registry.running() is None
    assert registry.get(job.id).error.startswith("RuntimeError")


# --- the line buffer ------------------------------------------------------------


def test_the_line_buffer_drops_its_oldest_and_says_so():
    """A runaway module must not grow the server's memory without bound, and a
    reader must be able to tell that it happened."""
    from pipeline.web import jobs as jobs_module

    job = Job(id=1, kind="run", label="x", args={})
    for n in range(jobs_module.MAX_LINES + 50):
        job.append("info", f"line {n}")

    assert job.dropped == 50
    assert len(job.lines) == jobs_module.MAX_LINES
    assert job.head()["lines"] == jobs_module.MAX_LINES + 50

    # Indices still mean what they meant: line 60 is line 60, not the 60th
    # surviving line.
    chunk, _ = job.since(59)
    assert chunk[0]["i"] == 60
    assert chunk[0]["text"] == "line 60"

    # Asking for something that has been trimmed away returns what survives
    # rather than an error or a wrong answer.
    chunk, _ = job.since(-1)
    assert chunk[0]["i"] == 50


def test_a_module_leaves_the_thread_name_it_found():
    """`execute_module` renames the running thread after the module, and the
    serial path runs on the caller's own thread. Left renamed, the CLI's main
    thread stays labelled with whichever module ran last -- and the job log,
    which decides what belongs to a run by thread name, starts accepting lines
    from threads that are no longer running anything."""
    from pipeline.registry import MODULE_REGISTRY as reg

    before = threading.current_thread().name
    seen = []

    def module(ctx):
        seen.append(threading.current_thread().name)

    reg["a_named"] = module
    try:
        runner.run_waves([["a_named"]], 1, _memory_settings(), None, True, None)
    finally:
        del reg["a_named"]

    assert seen == ["a_named"], "the thread should be named after the module while it runs"
    assert threading.current_thread().name == before


def _memory_settings():
    """Settings pointing at a scratch warehouse, for a run with no fixtures."""
    import tempfile
    from pathlib import Path

    from pipeline import db
    from pipeline.config import Settings

    tmp = Path(tempfile.mkdtemp())
    settings = Settings(
        contact_email="test@example.com",
        database_path=tmp / "warehouse.db",
        raw_archive_dir=tmp / "raw",
        migrations_dir=Path(__file__).resolve().parent.parent / "pipeline" / "migrations",
        logs_dir=tmp / "logs",
        default_rate_limit_seconds=0.0,
        _env_file=None,
    )
    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    conn.commit()
    conn.close()
    return settings


def test_a_jobs_log_only_carries_its_own_threads(client, monkeypatch):
    """The server keeps serving while a run goes on. Another tab's review
    decision is not part of this job's log."""
    import structlog

    release = threading.Event()
    seen = threading.Event()

    def slow(ctx):
        seen.set()
        release.wait(timeout=10)

    monkeypatch.setitem(MODULE_REGISTRY, "a_slow", slow)
    job_id = post(client, "/api/admin/run", {"module": "a_slow"}).json()["id"]
    assert seen.wait(timeout=10)

    # Logged from the test's thread, which is not one of the run's.
    structlog.get_logger().info("web.something_else", detail="not part of the run")
    release.set()
    assert wait_for(lambda: client.get(f"/api/admin/jobs/{job_id}").json()["state"]
                     != "running")

    text = " ".join(line["text"] for line
                     in client.get(f"/api/admin/jobs/{job_id}").json()["log"])
    assert "something_else" not in text


# --- the run is the CLI's run ---------------------------------------------------


def test_the_web_runs_modules_through_the_same_code_as_the_cli():
    """Not a style point. The connection per module, the rollback on failure,
    the audit-count deltas and the write-slot discipline are all in
    runner.run_waves, and a second implementation would drift from them."""
    import inspect

    from pipeline import cli

    assert runner.run_waves is admin.runner.run_waves
    assert "runner.run_waves" in inspect.getsource(cli._run_waves)
    assert "runner.run_waves" in inspect.getsource(admin.start_run)


def test_the_web_command_configures_the_logging_the_job_log_depends_on():
    """The capture reads the root logger, which is empty until
    `configure_logging` points structlog at stdlib. That call lives in the CLI
    command, one file away from the code that relies on it."""
    import inspect

    from pipeline import cli

    assert "configure_logging" in inspect.getsource(cli.web)
