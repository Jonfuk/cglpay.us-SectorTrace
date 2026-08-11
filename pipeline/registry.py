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
from typing import Callable

from pipeline.config import Settings

ModuleFn = Callable[["ModuleContext"], None]

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


@dataclass
class ModuleContext:
    conn: Connection
    settings: Settings
    since: str | None
    dry_run: bool
    limit: int | None

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


def register_module(name: str, supports_since: bool = False,
                     since_note: str = "") -> Callable[[ModuleFn], ModuleFn]:
    def decorator(fn: ModuleFn) -> ModuleFn:
        MODULE_REGISTRY[name] = fn
        MODULE_META[name] = ModuleMeta(
            name=name, supports_since=supports_since, since_note=since_note)
        return fn

    return decorator


def module_meta(name: str) -> ModuleMeta:
    return MODULE_META.get(name, ModuleMeta(name=name))


def discover_modules() -> None:
    """Import every submodule of pipeline.modules so their
    @register_module decorators run. Idempotent.
    """
    import pipeline.modules as modules_pkg

    for _finder, name, _is_pkg in pkgutil.iter_modules(modules_pkg.__path__):
        importlib.import_module(f"{modules_pkg.__name__}.{name}")
