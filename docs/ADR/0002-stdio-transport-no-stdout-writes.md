# ADR-0002: stdio transport implies no stdout writes from server code

**Status:** Accepted
**Date:** 2026-05-11
**Scope:** `src/tg_mcp/server.py`, `src/tg_mcp/logging_setup.py`,
`tests/test_server_stdio.py`

## Context

The MCP server speaks JSON-RPC over stdio: requests on stdin, responses on
stdout. Any byte written to stdout outside the protocol corrupts the
stream. A stray `print("debug")`, an exception traceback emitted by an
uncaught error, FastMCP's startup banner, or a default `StreamHandler`
attached by a third-party library are all sufficient to break the MCP
host's parser — and the failure surfaces as a generic "connector broken"
in the host UI, with no actionable signal in the failing host's logs.

The cost of this regression is asymmetric: cheap to introduce (one
`print`), expensive to diagnose (no error path leads back to the offending
write).

## Decision

No server code writes to stdout. Diagnostics are funneled through Python's
`logging` to a single `RotatingFileHandler` (1 MB × 5 files, default path
`~/.local/state/tg-mcp/server.log`). The constraint is enforced at three
levels:

1. **Library configuration.** `logging_setup.setup_logging()` removes any
   existing handlers from the root logger before attaching the file
   handler, so a third-party library that installed a `StreamHandler` at
   import time has its handler stripped before any log fires.
2. **FastMCP configuration.** `server.main()` calls `mcp.run(transport="stdio", show_banner=False)`
   to suppress FastMCP's banner. The companion silencing step,
   `server._route_fastmcp_logs_to_file()`, runs at **module-import time**
   of `tg_mcp.server` (right after `from fastmcp import FastMCP`, before
   `mcp = FastMCP(...)` is constructed). It strips the `RichHandler` that
   FastMCP installs on its own `fastmcp` logger and re-enables
   `propagate=True` so those messages reach the root file handler
   instead of stderr. Doing this at import time — rather than inside
   `main()` — matters because `mcp.run()` can be entered from places
   other than the `main()` entry point: the in-process stdio
   integration test imports `tg_mcp.server` and exercises the same
   `mcp` object, and any future alternate entry point (a wrapper
   script, an embedded launcher, a different transport) would
   otherwise need to remember to call the silencer manually. Tying the
   strip to module import makes the invariant a property of the module,
   not of one call site.
3. **Automated regression guard.** `tests/test_server_stdio.py` holds two
   tests against the real `python -m tg_mcp.server` subprocess.
   `test_stdout_is_silent_on_immediate_eof` runs the server with closed
   stdin and asserts `result.stdout == b""` and `result.stderr == b""` —
   it catches a stray `print` or `StreamHandler` that fires on boot
   even with no protocol traffic. `test_full_protocol_exchange_keeps_stdio_clean`
   drives a real `initialize` + `tools/list` + deliberately failing
   `tools/call` exchange, reads responses incrementally through a
   daemon-thread line reader, and asserts every stdout line parses as
   JSON-RPC 2.0 and stderr stays empty. The failing `tools/call` exercises
   `_CallLoggingMiddleware.on_call_tool` end-to-end including its
   exception branch, so a regression that adds a `print()` anywhere
   on the tool-dispatch path would surface here as a non-JSON line
   and fail the assertion. Both tests pass placeholder credentials so
   the server boots through `setup_logging` and `FastMCP.run` without
   needing a working session.

## Consequences

- Operators must tail the log file to see anything. There is no
  fallback console output, even at startup or on a fatal error during
  `main()`. The README documents `tail -f` and the default path.
- The regression test is the single point of detection. A new
  third-party dependency that installs a `StreamHandler` at import time
  will be caught by it on next run.
- Adding a feature that requires a one-shot stdout write (a CLI flag,
  a `--version`, a help banner) must happen **before** `mcp.run()` is
  called and must be paired with an early `sys.exit(...)` — never
  mid-server.
- The `scripts/login.py` helper is intentionally outside this rule:
  it is a separate process, never run inside the server, and it
  prints the session string to stdout by design with all prompts on
  stderr.

## Alternatives considered

- **Allow stderr writes, forbid only stdout.** Rejected as the default:
  some MCP hosts also surface stderr (Cowork's connector view did
  during testing), so noisy stderr corrupts the operator experience
  even if it does not corrupt the protocol. The test asserts both
  empty.
- **Trust library defaults; add a `print` ban via lint.** Rejected:
  the failure mode is third-party handlers attached at import time,
  which lint cannot see.
- **Use a non-stdio transport (HTTP, SSE).** Out of scope for v1; the
  spec calls for local stdio. Revisit if a remote deployment is ever
  needed.

## References

- Project `CLAUDE.md` — hard constraints section ("No stdout writes").
- `src/tg_mcp/server.py` — `_route_fastmcp_logs_to_file`, `main`.
- `src/tg_mcp/logging_setup.py` — handler-stripping idempotency.
- `tests/test_server_stdio.py` — the regression guard.
