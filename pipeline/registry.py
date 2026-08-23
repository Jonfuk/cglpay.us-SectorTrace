"""Module registration mechanism.

Each pipeline/modules/mNN_*.py file decorates its entry point with
@register_module("mNN_name") so the CLI can discover it without a
hand-maintained list. Modules are imported lazily (only when `run` needs the
registry populated) so scaffolding-only checkouts don't import modules that
don't exist yet.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from datetime import date
from sqlite3 import Connection
from typing import TYPE_CHECKING, Callable

from pipeline.config import Settings

ModuleFn = Callable[["ModuleContext"], None]

if TYPE_CHECKING:   # pragma: no cover
    from pipeline.console import ProgressReporter


def _null_reporter() -> "ProgressReporter":
    """Imported lazily so registry.py stays importable without rich — module
    discovery must not depend on the terminal layer.
    """
    from pipeline.console import NULL_REPORTER

    return NULL_REPORTER

MODULE_REGISTRY: dict[str, ModuleFn] = {}

# name -> capability metadata. Kept alongside the registry so the CLI can tell
# a caller when a flag will have no effect, rather than accepting it silently.
MODULE_META: dict[str, "ModuleMeta"] = {}


@dataclass(frozen=True)
class ModuleMeta:
    name: str
    # Whether the module actually filters on ctx.since. Declared per module so
    # `--since` cannot be quietly ignored: the CLI warns when it is passed to
    # a module that does not use it, which otherwise looks like a successful
    # filtered run over the whole source.
    supports_since: bool = False
    since_note: str = ""
    # Whether the module reads ctx.source to scope itself to a subset of its
    # own channels (currently just m01, whose live-API and CSV-archive
    # channels can be run independently). Declared for the same reason as
    # supports_since: so --api/--csv/--all passed to a module that ignores it
    # is a warning, not a silent no-op.
    supports_source: bool = False
    source_note: str = ""
    # Modules whose output this one reads. `run all` orders on these rather
    # than running alphabetically, which silently produced worse results:
    # m04 ran before m05 and so missed the company numbers CQC publishes, and
    # m09/m10 ran before m15 and so saw one authority website instead of 315.
    # A missing dependency is not fatal — each module degrades honestly — but
    # the run is worth less, in ways that look like success.
    depends_on: tuple[str, ...] = ()
    depends_note: str = ""


@dataclass
class ModuleContext:
    conn: Connection
    settings: Settings
    since: str | None
    dry_run: bool
    limit: int | None
    # "api" | "csv" | "kag" | "all" — which of a module's own channels to
    # run. Only m01 reads this today (see its module docstring); every other
    # module ignores it, so the default of "all" is a no-op for them.
    source: str = "all"
    # Write-only. A module reports progress through this and collects exactly
    # the same evidence whether or not anything is displaying it — the default
    # reporter is a no-op, so `ctx.track(...)` is a plain loop under cron.
    progress: "ProgressReporter" = field(default_factory=lambda: _null_reporter())

    def track(self, items, description: str, total: int | None = None):
        """Iterate `items`, advancing a progress bar if one is displayed."""
        return self.progress.track(items, description, total=total)

    def phase(self, text: str) -> None:
        """Say what this module is doing, for work that has no countable
        units yet. Write-only, like track().
        """
        self.progress.phase(text)

    def since_date(self) -> date | None:
        """`since` as a date, or None. Raises on an unparseable value rather
        than silently processing everything.
        """
        if not self.since:
            return None
        try:
            return date.fromisoformat(self.since)
        except ValueError as exc:
            raise ValueError(
                f"--since must be an ISO date (YYYY-MM-DD); got {self.since!r}") from exc

    def since_year(self) -> int | None:
        parsed = self.since_date()
        return parsed.year if parsed else None

    def is_before_since(self, value: str | None) -> bool:
        """True when an ISO-ish date string predates --since and should be
        skipped. Unparseable or missing dates are never skipped — dropping a
        record because its date could not be read would be a silent loss.
        """
        boundary = self.since_date()
        if boundary is None or not value:
            return False
        try:
            return date.fromisoformat(str(value)[:10]) < boundary
        except ValueError:
            return False


def register_module(name: str, supports_since: bool = False, since_note: str = "",
                     supports_source: bool = False, source_note: str = "",
                     depends_on: tuple[str, ...] = (),
                     depends_note: str = "") -> Callable[[ModuleFn], ModuleFn]:
    def decorator(fn: ModuleFn) -> ModuleFn:
        MODULE_REGISTRY[name] = fn
        MODULE_META[name] = ModuleMeta(
            name=name, supports_since=supports_since, since_note=since_note,
            supports_source=supports_source, source_note=source_note,
            depends_on=tuple(depends_on), depends_note=depends_note)
        return fn

    return decorator


def module_meta(name: str) -> ModuleMeta:
    return MODULE_META.get(name, ModuleMeta(name=name))


class DependencyCycleError(RuntimeError):
    """Declared dependencies form a cycle, so no run order exists."""


def resolve_run_order(names: list[str] | None = None) -> list[str]:
    """Modules in dependency order, alphabetical among equals.

    Alphabetical tie-breaking keeps the order deterministic, so two runs of
    the same checkout do the same work in the same sequence and a diff of two
    logs means something.

    Dependencies on modules outside `names` are ignored rather than pulled in:
    asking for a subset should run that subset, not silently expand it.
    """
    selected = list(MODULE_REGISTRY) if names is None else list(names)
    remaining = set(selected)

    ordered: list[str] = []
    satisfied: set[str] = set()

    while remaining:
        ready = sorted(
            name for name in remaining
            if all(dep in satisfied or dep not in remaining
                    for dep in module_meta(name).depends_on)
        )
        if not ready:
            raise DependencyCycleError(
                "Cannot order modules — declared dependencies form a cycle among: "
                f"{sorted(remaining)}")
        for name in ready:
            ordered.append(name)
            satisfied.add(name)
            remaining.discard(name)

    return ordered


def resolve_run_waves(names: list[str] | None = None) -> list[list[str]]:
    """The same order as `resolve_run_order`, grouped into waves.

    Every module in a wave has all its declared dependencies satisfied by
    earlier waves, so a wave can run concurrently. Flattening the result
    reproduces `resolve_run_order` exactly — the two must not disagree about
    what runs before what.

    Concurrency across modules is safe because the per-host rate limit is
    enforced process-wide (pipeline.http.HOST_CLOCK). Modules on different
    APIs proceed independently; the four that share www.gov.uk queue behind
    each other on that host and nowhere else.
    """
    selected = list(MODULE_REGISTRY) if names is None else list(names)
    remaining = set(selected)

    waves: list[list[str]] = []
    satisfied: set[str] = set()

    while remaining:
        ready = sorted(
            name for name in remaining
            if all(dep in satisfied or dep not in remaining
                    for dep in module_meta(name).depends_on)
        )
        if not ready:
            raise DependencyCycleError(
                "Cannot order modules — declared dependencies form a cycle among: "
                f"{sorted(remaining)}")
        waves.append(ready)
        satisfied.update(ready)
        remaining.difference_update(ready)

    return waves


def missing_dependencies(names: list[str]) -> dict[str, list[str]]:
    """Declared dependencies not included in the given selection, so the CLI
    can say what a partial run will be missing rather than quietly degrading.
    """
    selection = set(names)
    out: dict[str, list[str]] = {}
    for name in names:
        absent = [d for d in module_meta(name).depends_on if d not in selection]
        if absent:
            out[name] = absent
    return out


def discover_modules() -> None:
    """Import every submodule of pipeline.modules so their
    @register_module decorators run. Idempotent.
    """
    import pipeline.modules as modules_pkg

    for _finder, name, _is_pkg in pkgutil.iter_modules(modules_pkg.__path__):
        importlib.import_module(f"{modules_pkg.__name__}.{name}")
