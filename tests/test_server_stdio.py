"""Regression guard for the no-stdout invariant.

The MCP server speaks JSON-RPC over stdout. A stray ``print()``, a
StreamHandler, or FastMCP's banner would all corrupt the protocol and
break Cowork integration silently. This test launches the real
``python -m tg_mcp.server`` with stdin closed (EOF) and asserts that
**stdout stays empty**. It does not exercise tool calls — those live in
the per-tool tests with a fake client.
"""

from __future__ import annotations

import os
import subprocess
import sys


def test_stdout_is_silent(tmp_path):
    env = os.environ.copy()
    env["TG_LOG_PATH"] = str(tmp_path / "server.log")
    # The server must not require a working session to start up — credentials
    # are only consumed on the first tool call. We pass placeholders so the
    # process boots through setup_logging and FastMCP.run before EOF.
    env["TG_API_ID"] = "1"
    env["TG_API_HASH"] = "x"
    env["TG_SESSION_STRING"] = ""
    # Defensive: ensure dotenv loaded from cwd doesn't override.
    env["DOTENV_PATH"] = "/dev/null"

    result = subprocess.run(
        [sys.executable, "-m", "tg_mcp.server"],
        input=b"",
        capture_output=True,
        timeout=10,
        env=env,
    )

    assert result.stdout == b"", (
        f"stdout must be empty for stdio MCP transport, got {len(result.stdout)} "
        f"bytes: {result.stdout[:200]!r}"
    )
    # stderr should also be clean once FastMCP logs are routed to file.
    assert result.stderr == b"", (
        f"stderr expected empty (FastMCP logs go to file), got "
        f"{len(result.stderr)} bytes: {result.stderr[:200]!r}"
    )
