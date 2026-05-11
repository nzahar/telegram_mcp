"""Logging configuration tests.

The critical invariant: the MCP server speaks the JSON-RPC protocol over
stdout. Any log handler that writes to stdout/stderr corrupts that channel.
``test_setup_logging_keeps_stdio_silent`` is the regression guard.
"""

from __future__ import annotations

import logging
import sys
from io import StringIO

import pytest

from tg_mcp.logging_setup import setup_logging


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    path = tmp_path / "logs" / "server.log"
    monkeypatch.delenv("TG_LOG_PATH", raising=False)
    monkeypatch.delenv("TG_LOG_LEVEL", raising=False)
    yield path


def test_setup_logging_creates_parent_dir(log_dir):
    setup_logging(path=str(log_dir))
    assert log_dir.parent.is_dir()


def test_setup_logging_writes_to_file(log_dir):
    setup_logging(path=str(log_dir), level="DEBUG")
    logging.getLogger("tg_mcp.test").info("hello-from-test-1234")
    for h in logging.getLogger().handlers:
        h.flush()
    content = log_dir.read_text(encoding="utf-8")
    assert "hello-from-test-1234" in content
    assert "INFO" in content


def test_setup_logging_keeps_stdio_silent(log_dir, monkeypatch, capsys):
    setup_logging(path=str(log_dir))
    logging.getLogger("tg_mcp.test").info("must-not-leak")
    logging.getLogger("tg_mcp.test").error("must-not-leak-err")
    for h in logging.getLogger().handlers:
        h.flush()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_setup_logging_removes_preexisting_stream_handler(log_dir):
    # Simulate a polluted root (e.g. some import added a StreamHandler).
    root = logging.getLogger()
    polluted = logging.StreamHandler(sys.stdout)
    root.addHandler(polluted)
    setup_logging(path=str(log_dir))
    assert all(
        not isinstance(h, logging.StreamHandler)
        or h.__class__.__name__ == "RotatingFileHandler"
        for h in root.handlers
    )
    # The polluted handler is gone.
    assert polluted not in root.handlers


def test_setup_logging_idempotent_no_handler_growth(log_dir):
    for _ in range(5):
        setup_logging(path=str(log_dir))
    assert len(logging.getLogger().handlers) == 1


def test_setup_logging_respects_env_path(tmp_path, monkeypatch):
    env_path = tmp_path / "via-env" / "x.log"
    monkeypatch.setenv("TG_LOG_PATH", str(env_path))
    monkeypatch.delenv("TG_LOG_LEVEL", raising=False)
    resolved = setup_logging()
    assert resolved == env_path
    assert env_path.parent.is_dir()


def test_setup_logging_respects_env_level(log_dir, monkeypatch):
    monkeypatch.setenv("TG_LOG_LEVEL", "WARNING")
    setup_logging(path=str(log_dir))
    assert logging.getLogger().level == logging.WARNING


def test_setup_logging_invalid_level_falls_back_to_info(log_dir, monkeypatch):
    monkeypatch.setenv("TG_LOG_LEVEL", "BOGUS")
    setup_logging(path=str(log_dir))
    assert logging.getLogger().level == logging.INFO


def test_setup_logging_rotation_parameters_applied(log_dir):
    """RotatingFileHandler must be configured with the documented maxBytes and backupCount."""
    from logging.handlers import RotatingFileHandler
    from tg_mcp.logging_setup import BACKUP_COUNT, MAX_BYTES

    setup_logging(path=str(log_dir))
    root = logging.getLogger()
    rotating_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
    assert len(rotating_handlers) == 1, "expected exactly one RotatingFileHandler"
    h = rotating_handlers[0]
    assert h.maxBytes == MAX_BYTES
    assert h.backupCount == BACKUP_COUNT


def test_setup_logging_explicit_level_overrides_env(tmp_path, monkeypatch):
    """Explicit level= arg must win over TG_LOG_LEVEL env var."""
    monkeypatch.setenv("TG_LOG_LEVEL", "ERROR")
    monkeypatch.delenv("TG_LOG_PATH", raising=False)
    log_path = tmp_path / "override.log"
    setup_logging(path=str(log_path), level="DEBUG")
    assert logging.getLogger().level == logging.DEBUG
