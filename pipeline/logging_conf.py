"""structlog -> JSON lines, written to both stdout and logs/{module}.log."""
from __future__ import annotations

import logging
import sys

import structlog

from pipeline.config import get_settings


def configure_logging(module: str | None = None) -> None:
    settings = get_settings()
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = settings.logs_dir / f"{module or 'pipeline'}.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    stream_handler = logging.StreamHandler(sys.stdout)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    for handler in (stream_handler, file_handler):
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)

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
