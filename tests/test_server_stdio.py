"""Regression guards for the no-stdout invariant.

The MCP server speaks JSON-RPC over stdout. A stray ``print()``, a
StreamHandler, or FastMCP's banner would all corrupt the protocol and
break Cowork integration silently. These tests launch the real
``python -m tg_mcp.server`` as a subprocess and verify:

  1. With stdin closed immediately, stdout and stderr stay empty.
  2. During a real JSON-RPC exchange (initialize + tools/list + a
     deliberately failing tools/call), every byte on stdout parses as a
     newline-delimited JSON-RPC message and stderr stays empty. A stray
     ``print()`` inside any tool handler or middleware would surface as
     a non-JSON line and fail this test.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time


def _env(tmp_path) -> dict:
    env = os.environ.copy()
    env["TG_LOG_PATH"] = str(tmp_path / "server.log")
    env["TG_API_ID"] = "1"
    env["TG_API_HASH"] = "x"
    env["TG_SESSION_STRING"] = ""
    env["DOTENV_PATH"] = "/dev/null"
    return env


def _line(method: str, params: dict, msg_id: int | None = None) -> str:
    msg: dict = {"jsonrpc": "2.0", "method": method, "params": params}
    if msg_id is not None:
        msg["id"] = msg_id
    return json.dumps(msg) + "\n"


def test_stdout_is_silent_on_immediate_eof(tmp_path):
    """Server boots through setup_logging + FastMCP.run, sees EOF, exits clean."""
    result = subprocess.run(
        [sys.executable, "-m", "tg_mcp.server"],
        input=b"",
        capture_output=True,
        timeout=10,
        env=_env(tmp_path),
    )
    assert result.stdout == b"", (
        f"stdout must be empty for stdio MCP transport, got {len(result.stdout)} "
        f"bytes: {result.stdout[:200]!r}"
    )
    assert result.stderr == b"", (
        f"stderr expected empty (FastMCP logs go to file), got "
        f"{len(result.stderr)} bytes: {result.stderr[:200]!r}"
    )


def _read_n_lines(stream, n: int, total_timeout: float) -> list[bytes]:
    """Read up to ``n`` newline-terminated lines from ``stream`` within
    ``total_timeout`` seconds. Uses a daemon reader thread so we can give up
    on time instead of blocking forever if the server stops responding.
    """
    q: queue.Queue[bytes | None] = queue.Queue()

    def reader() -> None:
        while True:
            line = stream.readline()
            if not line:
                q.put(None)
                return
            q.put(line)

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    deadline = time.monotonic() + total_timeout
    out: list[bytes] = []
    while len(out) < n:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            item = q.get(timeout=remaining)
        except queue.Empty:
            break
        if item is None:
            break
        out.append(item)
    return out


def test_full_protocol_exchange_keeps_stdio_clean(tmp_path):
    """Drive a real init + tools/list + failing tools/call; assert every
    stdout line is valid JSON-RPC and nothing leaks to stderr.

    The failing tools/call exercises ``_CallLoggingMiddleware.on_call_tool``
    end-to-end (including its exception branch) — a regression that adds a
    ``print()`` anywhere on that path would surface here as a non-JSON
    line and fail this test. We read responses incrementally and only close
    stdin after the expected count arrives, so we don't race with FastMCP's
    EOF-triggered shutdown.
    """
    requests = "".join(
        [
            _line(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "stdio-test", "version": "0"},
                },
                msg_id=1,
            ),
            _line("notifications/initialized", {}),
            _line("tools/list", {}, msg_id=2),
            _line(
                "tools/call",
                {"name": "nonexistent_tool", "arguments": {}},
                msg_id=3,
            ),
        ]
    )

    proc = subprocess.Popen(
        [sys.executable, "-m", "tg_mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_env(tmp_path),
        bufsize=0,
    )
    try:
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(requests.encode())
        proc.stdin.flush()

        # 3 ids issued -> 3 responses expected (notifications produce no reply).
        lines = _read_n_lines(proc.stdout, n=3, total_timeout=15.0)

        proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        assert proc.stderr is not None
        stderr = proc.stderr.read()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    assert stderr == b"", f"stderr leak during protocol exchange: {stderr[:400]!r}"
    assert len(lines) == 3, (
        f"expected exactly 3 JSON-RPC responses, got {len(lines)}: "
        f"{[l[:200] for l in lines]!r}"
    )

    parsed = [json.loads(line) for line in lines]  # raises on garbage
    for msg in parsed:
        assert msg.get("jsonrpc") == "2.0"
        assert "id" in msg, f"expected response message with id, got {msg!r}"

    by_id = {m["id"]: m for m in parsed}
    assert "result" in by_id[1]
    assert by_id[1]["result"]["serverInfo"]["name"] == "tg-mcp"

    assert "result" in by_id[2]
    tool_names = [t["name"] for t in by_id[2]["result"]["tools"]]
    assert set(tool_names) == {"search_channels", "get_recent", "send_to_self"}

    # The since contract: search_channels declares `since` as required.
    search_tool = next(
        t for t in by_id[2]["result"]["tools"] if t["name"] == "search_channels"
    )
    assert "since" in search_tool["inputSchema"].get("required", [])

    # tools/call to an unknown tool comes back as a structured error,
    # not as a crash or stdout diagnostic.
    assert "result" in by_id[3]
    assert by_id[3]["result"].get("isError") is True
