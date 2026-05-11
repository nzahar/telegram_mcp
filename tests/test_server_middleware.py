"""Tests for _CallLoggingMiddleware in tg_mcp.server.

The middleware logs tool name and arg *keys* — never arg values.
This is especially critical for send_to_self.text: the body of a message
must never appear in the log file (privacy invariant).
"""

from __future__ import annotations

import logging
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_mcp.server import _CallLoggingMiddleware


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_context(name: str, arguments: dict) -> MagicMock:
    """Build a minimal context object matching the shape on_call_tool expects."""
    msg = MagicMock()
    msg.name = name
    msg.arguments = arguments
    ctx = MagicMock()
    ctx.message = msg
    return ctx


async def _collect_log_lines(caplog, name: str, arguments: dict) -> list[str]:
    """Run the middleware against a dummy call_next and return captured log lines."""
    middleware = _CallLoggingMiddleware()
    ctx = _make_context(name, arguments)

    async def call_next(_ctx):
        return MagicMock()

    with caplog.at_level(logging.INFO, logger="tg_mcp.server"):
        await middleware.on_call_tool(ctx, call_next)

    return [r.message for r in caplog.records]


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestCallLoggingMiddleware:
    async def test_logs_tool_name(self, caplog):
        lines = await _collect_log_lines(caplog, "send_to_self", {"text": "hello", "chat": "me"})
        assert any("send_to_self" in line for line in lines)

    async def test_logs_arg_keys_not_values(self, caplog):
        """arg_keys must appear in the log; arg values must not."""
        canary = "super_secret_message_body_xyzzy_12345"
        lines = await _collect_log_lines(
            caplog, "send_to_self", {"text": canary, "chat": "me", "tag": "news"}
        )
        all_output = "\n".join(lines)
        # Keys are logged.
        assert "text" in all_output
        assert "chat" in all_output
        # Value of 'text' must never appear.
        assert canary not in all_output

    async def test_arg_keys_are_sorted(self, caplog):
        """The middleware sorts arg_keys so log lines are deterministic."""
        lines = await _collect_log_lines(
            caplog, "search_channels", {"since": "1h", "channels": ["@x"], "query": "foo"}
        )
        tool_call_line = next(line for line in lines if "tool_call" in line)
        # The bracket notation appears with sorted order.
        assert "['channels', 'query', 'since']" in tool_call_line

    async def test_logs_elapsed_ms_on_success(self, caplog):
        lines = await _collect_log_lines(caplog, "get_recent", {"channel": "@ch"})
        assert any("elapsed_ms" in line for line in lines)

    async def test_logs_tool_error_and_reraises(self, caplog):
        """Middleware must re-raise exceptions and log tool_error with elapsed_ms."""
        middleware = _CallLoggingMiddleware()
        ctx = _make_context("search_channels", {"channels": ["@x"]})

        async def call_next_raises(_ctx):
            raise RuntimeError("upstream failure")

        with caplog.at_level(logging.ERROR, logger="tg_mcp.server"):
            with pytest.raises(RuntimeError, match="upstream failure"):
                await middleware.on_call_tool(ctx, call_next_raises)

        assert any("tool_error" in r.message for r in caplog.records)

    async def test_empty_arguments_dict_handled(self, caplog):
        """None or empty arguments dict must not crash the middleware."""
        lines = await _collect_log_lines(caplog, "some_tool", {})
        assert any("some_tool" in line for line in lines)

    async def test_none_arguments_handled(self, caplog):
        """arguments=None (valid FastMCP edge case) must not crash."""
        middleware = _CallLoggingMiddleware()
        ctx = _make_context("some_tool", {})
        ctx.message.arguments = None  # override to None

        async def call_next(_ctx):
            return MagicMock()

        with caplog.at_level(logging.INFO, logger="tg_mcp.server"):
            await middleware.on_call_tool(ctx, call_next)

        lines = [r.message for r in caplog.records]
        assert any("some_tool" in line for line in lines)


class TestMiddlewareTextNotInLogFile:
    """Integration-style check: write to a real log file, assert text value absent."""

    def test_send_text_never_reaches_log_file(self, tmp_path):
        """Simulate middleware logging via a real RotatingFileHandler; assert canary absent."""
        from logging.handlers import RotatingFileHandler
        from tg_mcp.logging_setup import MAX_BYTES, BACKUP_COUNT

        log_file = tmp_path / "test_server.log"
        handler = RotatingFileHandler(
            log_file, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(message)s"))

        server_logger = logging.getLogger("tg_mcp.server")
        original_handlers = server_logger.handlers[:]
        original_propagate = server_logger.propagate
        server_logger.handlers = [handler]
        server_logger.propagate = False
        server_logger.setLevel(logging.DEBUG)

        try:
            import asyncio

            canary = "CANARY_TEXT_MUST_NOT_APPEAR_IN_LOG_9876"

            async def run():
                middleware = _CallLoggingMiddleware()
                ctx = _make_context("send_to_self", {"text": canary, "chat": "me"})

                async def call_next(_ctx):
                    return MagicMock()

                await middleware.on_call_tool(ctx, call_next)

            asyncio.run(run())
            handler.flush()

            content = log_file.read_text(encoding="utf-8")
            assert canary not in content, (
                f"Canary text '{canary}' found in log file — "
                "middleware is leaking send_to_self.text values"
            )
            # Sanity: the tool name WAS logged.
            assert "send_to_self" in content
        finally:
            server_logger.handlers = original_handlers
            server_logger.propagate = original_propagate
            handler.close()
