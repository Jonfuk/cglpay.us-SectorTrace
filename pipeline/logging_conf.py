"""structlog -> JSON lines in logs/{module}.log, and only what a person needs
on the terminal.

These are two different artefacts and they were being conflated. The log file
is the audit trail: every request, every URL, every retrieval timestamp, in
full, because that is what makes a figure defensible six months later. The
terminal is for the person watching a four-hour crawl, and a line per HTTP
request is not information at that scale — it is a wall of text scrolling past
faster than anyone can read, and it scrolls the progress display away with it.

So: the file keeps everything at INFO. The console gets WARNING and above,
routed through the same Rich console the progress bars use, so a genuine
warning appears *above* the bars instead of corrupting them. Nothing is lost;
`http.get` is still in the file for every single request.

**Rotation, and what it does and does not put at risk (O-03).** Nothing ever
pruned these files. A per-module log is now capped and rolls over into
`.log.1`, `.log.2` and so on, oldest discarded — which is a deletion, and this
project does not delete evidence, so it is worth being exact about what is
being discarded. The provenance that makes a figure defensible lives in the
warehouse (`source_url`, `retrieved_at`, `payload_sha256`) and in the archived
bytes under `data/raw/`. This file is the *operational* record: what ran, what
it asked for, and what went wrong at the time. Losing the oldest of it costs
the ability to reconstruct a run from months ago; it costs nothing that a
published figure rests on. The ceiling is a setting, so an operator who
disagrees can raise it rather than patch this.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

import structlog

from pipeline.config import get_settings


def configure_logging(module: str | None = None, console_level: int = logging.WARNING) -> None:
    settings = get_settings()
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = settings.logs_dir / f"{module or 'pipeline'}.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    # The audit trail. Unfiltered, and the only place per-request detail lives
    # -- but bounded now: see the module docstring for what a discarded
    # generation does and does not take with it.
    #
    # Rotation is by size rather than by day. These logs are written in bursts
    # -- one long crawl, then nothing for a week -- so a daily roll produces a
    # directory of empty files and still lets one four-hour run write without
    # limit, which is the failure mode this is for.
    #
    # `delay=True` so opening a log is not the act that creates it: several
    # commands configure logging as a matter of course and would otherwise
    # each leave an empty file named after a module that never ran.
    file_handler = RotatingFileHandler(
        log_file, encoding="utf-8", delay=True,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count)
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    file_handler.setLevel(logging.INFO)
    root.addHandler(file_handler)

    # The terminal. RichHandler is used rather than a plain StreamHandler
    # because it cooperates with an active Progress display — it prints above
    # the bars rather than interleaving with them mid-redraw.
    from rich.logging import RichHandler

    from pipeline.console import console

    console_handler = RichHandler(console=console(), show_path=False,
                                   rich_tracebacks=True, markup=False)
    console_handler.setLevel(console_level)
    root.addHandler(console_handler)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
