"""Running different APIs at once.

The pipeline talks to eleven independent backends. Only www.gov.uk is shared —
by m02, m07, m11 and m13 — and the per-host rate limit is enforced
process-wide, so those four queue behind each other on that host and nowhere
else. Everything else can proceed at the same time without any source seeing a
faster request rate than it would have alone.

What must survive the concurrency:

  * a module never starts before the module whose output it reads has
    finished — m04 after m03/m05, m09/m10 after m15, everything after m00;
  * the summary reads the same way twice, whichever API answered first;
  * one module failing costs that module, not the run, and not the work the
    others already committed.
"""
from __future__ import annotations

import threading
import time

import pytest

from pipeline import cli as cli_module
from pipeline import console as ui
from pipeline.registry import (
    MODULE_REGISTRY,
    DependencyCycleError,
    ModuleMeta,
    discover_modules,
    resolve_run_order,
    resolve_run_waves,
)


@pytest.fixture(scope="module", autouse=True)
def _discovered():
    discover_modules()


# --- waves agree with the order they replace ------------------------------------

def test_flattening_the_waves_reproduces_the_run_order():
    """Two functions deciding what runs before what must not disagree."""
    assert [name for wave in resolve_run_waves() for name in wave] == resolve_run_order()


def test_every_dependency_lands_in_an_earlier_wave():
    from pipeline.registry import module_meta

    position = {name: index
                for index, wave in enumerate(resolve_run_waves())
                for name in wave}
    for name, wave_index in position.items():
        for dependency in module_meta(name).depends_on:
            assert position[dependency] < wave_index, \
                f"{name} shares a wave with (or precedes) its dependency {dependency}"


def test_geography_is_alone_in_needing_to_go_first():
    """Everything joins to the authorities table, so m00 must be in the first
    wave — otherwise concurrency would race it.
    """
    assert "m00_geography" in resolve_run_waves()[0]


def test_the_first_wave_is_worth_parallelising():
    """If every wave held one module this would all be pointless."""
    assert len(resolve_run_waves()[0]) >= 2


def test_a_cycle_raises_rather_than_picking_waves(monkeypatch):
    from pipeline import registry

    monkeypatch.setitem(registry.MODULE_META, "x", ModuleMeta(name="x", depends_on=("y",)))
    monkeypatch.setitem(registry.MODULE_META, "y", ModuleMeta(name="y", depends_on=("x",)))
    with pytest.raises(DependencyCycleError):
        resolve_run_waves(["x", "y"])


def test_a_subset_is_not_silently_expanded():
    waves = resolve_run_waves(["m04_companies", "m00_geography"])
    assert [n for wave in waves for n in wave] == ["m00_geography", "m04_companies"]


# --- the execution engine -------------------------------------------------------

def _settings(tmp_path):
    from pathlib import Path

    from pipeline.config import Settings

    return Settings(
        contact_email="t@example.com", database_path=tmp_path / "w.db",
        raw_archive_dir=tmp_path / "raw", logs_dir=tmp_path / "logs",
        migrations_dir=Path(__file__).resolve().parent.parent / "pipeline" / "migrations",
        _env_file=None)


@pytest.fixture
def prepared(tmp_path):
    from pipeline import db

    settings = _settings(tmp_path)
    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    conn.commit()
    conn.close()
    return settings


def _run_waves(waves, jobs, settings, registry_patch, monkeypatch):
    for name, fn in registry_patch.items():
        monkeypatch.setitem(MODULE_REGISTRY, name, fn)
    with ui.progress() as bar:
        return cli_module._run_waves(waves, jobs, settings, None, False, None, bar)


def test_modules_in_a_wave_actually_overlap(prepared, monkeypatch):
    """The point of the exercise. Four modules on four different APIs should
    be in flight together, not one after another.
    """
    live = 0
    peak = 0
    lock = threading.Lock()

    def make(_name):
        def module(ctx):
            nonlocal live, peak
            with lock:
                live += 1
                peak = max(peak, live)
            time.sleep(0.05)
            with lock:
                live -= 1
        return module

    names = ["a_one", "a_two", "a_three", "a_four"]
    _run_waves([names], jobs=4, settings=prepared,
                registry_patch={n: make(n) for n in names}, monkeypatch=monkeypatch)
    assert peak >= 2, "modules in one wave ran strictly one after another"


def test_a_later_wave_never_starts_before_an_earlier_one_finishes(prepared, monkeypatch):
    """The correctness constraint. m04 reading company numbers m05 has not
    written yet would silently produce a worse run, exactly as it did when the
    order was alphabetical.
    """
    events: list[str] = []
    lock = threading.Lock()

    def make(name):
        def module(ctx):
            with lock:
                events.append(f"start {name}")
            time.sleep(0.03)
            with lock:
                events.append(f"end {name}")
        return module

    names = ["a_first", "a_second", "b_later"]
    _run_waves([["a_first", "a_second"], ["b_later"]], jobs=4, settings=prepared,
                registry_patch={n: make(n) for n in names}, monkeypatch=monkeypatch)

    assert events.index("start b_later") > events.index("end a_first")
    assert events.index("start b_later") > events.index("end a_second")


def test_the_summary_order_does_not_depend_on_who_answered_first(prepared, monkeypatch):
    def make(delay):
        def module(ctx):
            time.sleep(delay)
        return module

    names = ["a_slow", "a_medium", "a_fast"]
    summary = _run_waves(
        [names], jobs=3, settings=prepared,
        registry_patch={"a_slow": make(0.09), "a_medium": make(0.05), "a_fast": make(0.0)},
        monkeypatch=monkeypatch)
    assert [row["module"] for row in summary] == names


def test_one_module_failing_does_not_stop_the_others(prepared, monkeypatch):
    def ok(ctx):
        ctx.conn.execute(
            "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
            "VALUES ('a_ok','x','y','2026-01-01')")

    def boom(ctx):
        raise RuntimeError("that API is down")

    summary = _run_waves([["a_boom", "a_ok"]], jobs=2, settings=prepared,
                          registry_patch={"a_boom": boom, "a_ok": ok},
                          monkeypatch=monkeypatch)
    by_name = {row["module"]: row for row in summary}
    assert by_name["a_boom"]["status"] == "failed"
    assert isinstance(by_name["a_boom"]["error"], RuntimeError)
    assert by_name["a_ok"]["status"] == "ok"


def test_a_failing_module_rolls_back_only_its_own_writes(prepared, monkeypatch):
    """A connection per module. With one shared connection a rollback could
    discard work belonging to whatever else had touched it.
    """
    from pipeline import db

    def ok(ctx):
        ctx.conn.execute(
            "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
            "VALUES ('a_keeper','kept','y','2026-01-01')")

    def boom(ctx):
        ctx.conn.execute(
            "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
            "VALUES ('a_loser','discarded','y','2026-01-01')")
        raise RuntimeError("failed after writing")

    _run_waves([["a_keeper"], ["a_loser"]], jobs=1, settings=prepared,
                registry_patch={"a_keeper": ok, "a_loser": boom}, monkeypatch=monkeypatch)

    conn = db.get_connection(prepared)
    try:
        kept = {r["item_type"] for r in conn.execute("SELECT item_type FROM review_queue")}
    finally:
        conn.close()
    assert "kept" in kept
    assert "discarded" not in kept


def test_row_counts_are_attributed_to_the_module_that_wrote_them(prepared, monkeypatch):
    """Per-module connections make total_changes exact; a shared connection
    would have mixed concurrent modules' counts together.
    """
    def writer(label, rows):
        # A distinct label per writer: review_queue deduplicates on
        # (module, item_type, raw_value), so two writers sharing a label would
        # collide on the unique index rather than testing anything.
        def module(ctx):
            for i in range(rows):
                ctx.conn.execute(
                    "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
                    "VALUES (?,?,?,?)", (label, "t", str(i), "2026-01-01"))
        return module

    summary = _run_waves([["a_three", "a_seven"]], jobs=2, settings=prepared,
                          registry_patch={"a_three": writer("three", 3),
                                           "a_seven": writer("seven", 7)},
                          monkeypatch=monkeypatch)
    rows = {row["module"]: row["rows"] for row in summary}
    assert rows["a_three"] == 3
    assert rows["a_seven"] == 7


def test_jobs_of_one_is_still_fully_serial(prepared, monkeypatch):
    live = 0
    peak = 0
    lock = threading.Lock()

    def module(ctx):
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(0.02)
        with lock:
            live -= 1

    names = ["a_one", "a_two", "a_three"]
    _run_waves([names], jobs=1, settings=prepared,
                registry_patch={n: module for n in names}, monkeypatch=monkeypatch)
    assert peak == 1


# --- --limit 0 ------------------------------------------------------------------------

def test_limit_zero_is_refused_rather_than_reinterpreted(tmp_path, monkeypatch):
    """Every module tests `if ctx.limit:`, so 0 is falsy and reads as "no
    limit at all". Typing --limit 0 to fetch nothing launched a full live
    crawl instead — found by doing exactly that.
    """
    from typer.testing import CliRunner

    settings = _settings(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.app, ["run", "all", "--limit", "0"])
    assert result.exit_code == 1
    assert "--limit must be 1 or more" in result.output


def test_a_real_limit_is_still_accepted(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    settings = _settings(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    monkeypatch.setitem(MODULE_REGISTRY, "m05_cqc", lambda ctx: None)

    result = CliRunner().invoke(cli_module.app, ["run", "m05_cqc", "--limit", "5"])
    assert "--limit must be" not in result.output


def test_jobs_below_one_is_rejected_by_the_option(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    settings = _settings(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.app, ["run", "all", "--jobs", "0"])
    assert result.exit_code != 0


# --- discoverability ------------------------------------------------------------------

def test_both_start_scripts_document_jobs():
    """The scripts pass every argument through, so --jobs already works from
    them. What was missing was any way to find that out.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for script in ("start.sh", "start.cmd"):
        text = (root / script).read_text(encoding="utf-8")
        assert "--jobs" in text, f"{script} never mentions --jobs"


def test_a_serial_run_all_says_the_waves_are_not_being_used_concurrently(
        tmp_path, monkeypatch):
    """Printing waves could reasonably be read as "this run is parallel".
    With the default --jobs 1 it is not, and it says so.
    """
    from typer.testing import CliRunner

    settings = _settings(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    for name in list(MODULE_REGISTRY):
        monkeypatch.setitem(MODULE_REGISTRY, name, lambda ctx: None)

    output = CliRunner().invoke(cli_module.app, ["run", "all"]).output
    assert "one at a time" in output
    assert "--jobs" in output, "a serial run never mentions how to parallelise it"


def test_a_parallel_run_all_does_not_print_the_serial_hint(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    settings = _settings(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    for name in list(MODULE_REGISTRY):
        monkeypatch.setitem(MODULE_REGISTRY, name, lambda ctx: None)

    output = CliRunner().invoke(cli_module.app, ["run", "all", "--jobs", "4"]).output
    assert "4 at a time" in output
    assert "running serially" not in output


# --- the display is never blank --------------------------------------------------------

def test_a_module_that_reports_no_progress_still_shows_a_bar(prepared, monkeypatch):
    """The bug as reported: `run all --jobs 8` printed the waves and then
    showed nothing at all.

    Only m09, m10 and m15 call ctx.track(), and wave 1 is m00, m02, m03, m06
    and m08 — so the display added no tasks and rendered a blank screen for
    however long the first wave took. A progress system that shows nothing
    during the first twenty minutes of a run is not a progress system.
    """
    seen: list[list[str]] = []

    def module(ctx):
        # Snapshot what the display is showing from inside the module.
        seen.append([t.description for t in bar.tasks])

    with ui.progress() as bar:
        monkeypatch.setitem(MODULE_REGISTRY, "a_silent", module)
        cli_module._run_waves([["a_silent"]], 1, prepared, None, False, None, bar)

    assert seen, "the module never ran"
    assert "a_silent" in seen[0], f"no task for the running module: {seen[0]}"
    assert "all modules" in seen[0], "no overall task"


def test_the_overall_bar_counts_every_module_across_every_wave(prepared, monkeypatch):
    finished: list[int] = []

    def module(ctx):
        finished.append(1)

    names = ["a_one", "a_two", "a_three"]
    with ui.progress() as bar:
        for name in names:
            monkeypatch.setitem(MODULE_REGISTRY, name, module)
        cli_module._run_waves([["a_one", "a_two"], ["a_three"]], 2, prepared,
                               None, False, None, bar)
        overall = [t for t in bar.tasks if t.description == "all modules"]
        assert overall and overall[0].total == 3
        assert overall[0].completed == 3


def test_a_modules_task_is_removed_when_it_finishes(prepared, monkeypatch):
    """Otherwise a sixteen-module run ends with sixteen dead bars on screen."""
    def module(ctx):
        pass

    with ui.progress() as bar:
        monkeypatch.setitem(MODULE_REGISTRY, "a_done", module)
        cli_module._run_waves([["a_done"]], 1, prepared, None, False, None, bar)
        assert [t.description for t in bar.tasks] == ["all modules"]


def test_a_failing_modules_task_is_also_removed(prepared, monkeypatch):
    def boom(ctx):
        raise RuntimeError("no")

    with ui.progress() as bar:
        monkeypatch.setitem(MODULE_REGISTRY, "a_boom", boom)
        cli_module._run_waves([["a_boom"]], 1, prepared, None, False, None, bar)
        assert [t.description for t in bar.tasks] == ["all modules"]


# --- the whole CLI path, with modules that actually write ------------------------
#
# Every other test here replaces modules with `lambda ctx: None`, which is why
# none of them could catch the failure that mattered: `run all --jobs 4`
# reporting "database is locked" against twelve of seventeen modules. Stubs
# that write nothing never contend for the write slot.

def test_a_parallel_wave_of_writing_modules_all_commit(tmp_path, monkeypatch):
    """The real _run_waves, with modules that seed providers and write.

    Reproduces the shape of the failing run: one module whose own work takes a
    while, and a wave of others starting at the same moment. Before the fix,
    the provider seed each of them wrote on startup was left uncommitted, so
    the first module to open a transaction held the database's only write slot
    across its whole run and the rest died on the busy handler.

    Given a busy timeout of two seconds rather than the real two minutes, and
    a slow module that outlasts it. Without that this test has no teeth: eight
    modules waiting politely for a second and a half all succeed against a
    120-second timeout whether the bug is present or not — which is exactly
    why the original failure needed a four-hour run to show itself.
    """
    import time

    from pipeline import db, providers
    from pipeline import console as ui

    settings = _settings(tmp_path)
    setup = db.get_connection(settings)
    db.apply_migrations(setup, settings.migrations_dir)
    setup.commit()
    setup.close()

    def make(name, hold):
        def module(ctx):
            providers.seed_providers(ctx.conn, commit=not ctx.dry_run)
            time.sleep(hold)
            ctx.conn.execute(
                "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
                "VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
                (name, "wave", name, "2026-01-01"))
        return module

    names = [f"m{i:02d}_writer" for i in range(8)]
    for index, name in enumerate(names):
        monkeypatch.setitem(MODULE_REGISTRY, name, make(name, 5.0 if index == 0 else 0.1))

    monkeypatch.setattr(db, "BUSY_TIMEOUT_MS", 2_000)
    with ui.progress() as bar:
        summary = cli_module._run_waves([names], 8, settings, None, False, None, bar)

    failed = [row for row in summary if row["status"] == "failed"]
    assert failed == [], (
        f"{len(failed)} of {len(names)} modules in one wave failed: "
        f"{[(r['module'], repr(r.get('error'))) for r in failed[:3]]}")

    check = db.get_connection(settings)
    try:
        written = check.execute(
            "SELECT COUNT(*) c FROM review_queue WHERE item_type='wave'").fetchone()["c"]
    finally:
        check.close()
    assert written == len(names), "a module reported success without its row landing"
