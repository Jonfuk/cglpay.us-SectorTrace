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
from dataclasses import dataclass
from sqlite3 import Connection
from typing import Callable

from pipeline.config import Settings

ModuleFn = Callable[["ModuleContext"], None]

MODULE_REGISTRY: dict[str, ModuleFn] = {}


@dataclass
class ModuleContext:
    conn: Connection
    settings: Settings
    since: str | None
    dry_run: bool
    limit: int | None


def register_module(name: str) -> Callable[[ModuleFn], ModuleFn]:
    def decorator(fn: ModuleFn) -> ModuleFn:
        MODULE_REGISTRY[name] = fn
        return fn

    return decorator


def discover_modules() -> None:
    """Import every submodule of pipeline.modules so their
    @register_module decorators run. Idempotent.
    """
    import pipeline.modules as modules_pkg

    for _finder, name, _is_pkg in pkgutil.iter_modules(modules_pkg.__path__):
        importlib.import_module(f"{modules_pkg.__name__}.{name}")
