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
"""
from __future__ import annotations

import logging

import structlog

from pipeline.config import get_settings


def configure_logging(module: str | None = None, console_level: int = logging.WARNING) -> None:
    settings = get_settings()
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = settings.logs_dir / f"{module or 'pipeline'}.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    # The audit trail. Unfiltered, and the only place per-request detail lives.
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
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
