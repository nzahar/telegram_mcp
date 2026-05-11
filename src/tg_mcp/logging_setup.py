"""Rotating-file logging configuration.

The MCP server uses stdio as transport — any handler that writes to
stdout/stderr corrupts the protocol. This module installs a single
``RotatingFileHandler`` on the root logger and **never** attaches a
``StreamHandler``. See ``tests/test_logging.py`` for the silence guard.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


DEFAULT_LOG_PATH = Path.home() / ".local" / "state" / "tg-mcp" / "server.log"
DEFAULT_LEVEL = "INFO"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 5

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _resolve_path(explicit: Optional[str]) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("TG_LOG_PATH")
    if env:
        return Path(env).expanduser()
    return DEFAULT_LOG_PATH


def _resolve_level(explicit: Optional[str]) -> int:
    raw = explicit or os.environ.get("TG_LOG_LEVEL") or DEFAULT_LEVEL
    return logging.getLevelNamesMapping().get(raw.upper(), logging.INFO)


def setup_logging(
    path: Optional[str] = None,
    level: Optional[str] = None,
) -> Path:
    """Configure the root logger with a single rotating file handler.

    Existing handlers on the root logger are removed first so that repeated
    calls (tests, restarts) are idempotent and never accumulate a stray
    StreamHandler. The parent directory is created if missing.

    Returns the resolved log path.
    """
    log_path = _resolve_path(path)
    log_level = _resolve_level(level)

    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()

    handler = RotatingFileHandler(
        log_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(handler)
    root.setLevel(log_level)
    return log_path
