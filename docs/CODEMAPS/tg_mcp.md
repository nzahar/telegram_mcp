## Codemap: `tg_mcp` package

**Last Updated:** 2026-05-11
**Structure Hash:** 8a1f912f147221edae2a564438abf87e
**Scope:** `src/tg_mcp/`, `scripts/login.py`, `tests/`

### Module graph

| Module | Path | Imports from package | Public surface |
|---|---|---|---|
| `tg_mcp` | `src/tg_mcp/__init__.py` | — | `__version__` (`"0.1.0"`) |
| `tg_mcp.models` | `src/tg_mcp/models.py` | — | `ChannelRef`, `Message`, `ErrorEntry`, `ReadResult`, `SendResult` |
| `tg_mcp.formatting` | `src/tg_mcp/formatting.py` | — | `TELEGRAM_MESSAGE_LIMIT`, `escape_md_v2`, `split_for_telegram`, `prepend_tag` |
| `tg_mcp.logging_setup` | `src/tg_mcp/logging_setup.py` | — | `setup_logging`, `DEFAULT_LOG_PATH`, `DEFAULT_LEVEL`, `MAX_BYTES`, `BACKUP_COUNT` |
| `tg_mcp.client` | `src/tg_mcp/client.py` | `.models` (for `ChannelRef`) | `ChannelRef` (re-exported from `.models`), `ChannelResolutionError`, `FloodLimitExceeded`, `get_client`, `shutdown`, `parse_since`, `resolve_channel`, `with_flood_retry` |
| `tg_mcp.tools` | `src/tg_mcp/tools.py` | `.client`, `.formatting`, `.models` | `search_channels`, `get_recent`, `send_to_self` |
| `tg_mcp.server` | `src/tg_mcp/server.py` | `.client` (as `tg_client`), `.tools`, `.logging_setup` | `mcp` (FastMCP instance), `main` |

`scripts/login.py` is intentionally standalone and does **not** import the `tg_mcp` package; it only depends on `telethon`.

### External dependencies (from `pyproject.toml`)

Runtime: `telethon>=1.36`, `fastmcp>=3.0,<4` (the 3.x `Middleware` API is used in `server.py`), `pydantic>=2.0`, `python-dotenv>=1.0`.
Dev: `pytest>=8.0`, `pytest-asyncio>=0.23`.

### Models (`tg_mcp.models`)

| Class | Fields |
|---|---|
| `ChannelRef` (alias) | `str | int` |
| `Message` | `channel: ChannelRef`, `id: int`, `date: datetime`, `text: str`, `link: Optional[str]`, `views: Optional[int]` |
| `ErrorEntry` | `channel: ChannelRef`, `error: str`, `detail: Optional[str]` |
| `ReadResult` | `items: list[Message \| ErrorEntry]`, `partial: bool` |
| `SendResult` | `chat: ChannelRef`, `message_ids: list[int]`, `link: Optional[str]`, `partial: bool` |

`ErrorEntry.error` codes emitted by the package: `channel_not_found`, `channel_private`, `username_invalid`, `flood_wait_exceeded`, `internal_error`.

### MCP tool surface (`tg_mcp.server`)

Registered via `mcp.tool(...)` on a `FastMCP("tg-mcp", lifespan=_lifespan, middleware=[_CallLoggingMiddleware()])`:

| Tool | Signature | Returns |
|---|---|---|
| `search_channels` | `(channels: list[ChannelRef], since: str, query: str = "", limit_per_channel: int = 50)` | `ReadResult` |
| `get_recent` | `(channel: ChannelRef, limit: int = 30)` | `ReadResult` |
| `send_to_self` | `(text: str, chat: ChannelRef = "me", tag: Optional[str] = None)` | `SendResult` |

`search_channels.since` is **required by design** (see ADR-0004) — callers cannot accidentally request the full history of a channel. The documented escape hatch is an explicit wide window like `"36500d"`, which is honest about its meaning at the call site instead of hiding behind a defaulted `None`.

Entrypoint: `python -m tg_mcp.server` calls `main()` → `load_dotenv()` → `setup_logging()` → `mcp.run(transport="stdio", show_banner=False)`. `_route_fastmcp_logs_to_file()` is **not** part of the `main()` chain — it runs at module-import time of `tg_mcp.server` (right after `from fastmcp import FastMCP`) so any entry path (direct `python -m`, in-process `import tg_mcp.server; mcp.run()`, future alternate entry points) inherits the clean logger configuration without having to go through `main`.

### Environment variables consumed

| Variable | Read in | Purpose |
|---|---|---|
| `TG_API_ID` | `client.get_client`, `scripts/login.py` | Telegram API id (int) |
| `TG_API_HASH` | `client.get_client`, `scripts/login.py` | Telegram API hash |
| `TG_SESSION_STRING` | `client.get_client` | Telethon `StringSession` source |
| `TG_LOG_PATH` | `logging_setup._resolve_path` | Override log file path (default `~/.local/state/tg-mcp/server.log`) |
| `TG_LOG_LEVEL` | `logging_setup._resolve_level` | Root logger level (default `INFO`) |

### Test layout

| Test file | Subject |
|---|---|
| `tests/conftest.py` | `FakeClient`, `FakeEntity`, `FakeRawMessage`, `FakeSentMessage`, `fake_client`, `fast_flood_retry`, `flood` fixtures |
| `tests/test_send.py` | `formatting`: escape, split-by-paragraph/sentence/char, `prepend_tag` |
| `tests/test_logging.py` | `logging_setup.setup_logging`: file write, stdout/stderr silence, env-var routing |
| `tests/test_client.py` | `client.get_client` singleton, `shutdown`, `resolve_channel`, `with_flood_retry`, `TestGetClientStaleReconnect` (network-disconnect error swallowed; programmer error propagates — documents the narrow `(ConnectionError, OSError)` catch in stale-client cleanup) |
| `tests/test_since_parsing.py` | `client.parse_since` happy + error paths |
| `tests/test_search.py` | `tools.search_channels` (happy path, ErrorEntry, flood retry, partial) |
| `tests/test_get_recent.py` | `tools.get_recent` |
| `tests/test_send_tool.py` | `tools.send_to_self` (split → multi-send, partial on flood, tag, link rules) |
| `tests/test_server_stdio.py` | Regression guards: (1) `test_stdout_is_silent_on_immediate_eof` — real `python -m tg_mcp.server` with closed stdin produces 0 bytes on stdout/stderr; (2) `test_full_protocol_exchange_keeps_stdio_clean` — drives a real initialize + tools/list + failing tools/call against the subprocess, asserts every stdout line parses as JSON-RPC 2.0 and stderr stays empty (exercises `_CallLoggingMiddleware.on_call_tool` end-to-end including its exception branch) |
| `tests/test_server_middleware.py` | `_CallLoggingMiddleware` unit tests: tool name logged, arg keys logged but values never reach the log file (privacy invariant for `send_to_self.text` — verified with a canary on a real `RotatingFileHandler`), keys sorted deterministically, elapsed_ms on success, exception logged as `tool_error` and re-raised, `arguments=None` handled. `TestFastMCPLoggerStrip`: import-time `_route_fastmcp_logs_to_file` clears `logging.getLogger("fastmcp").handlers` and sets `propagate=True` (regression guard for a future FastMCP that attaches its handler after our strip point) |
| `tests/test_login_script.py` | `scripts/login.py` argparse / env handling |
| `tests/test_integration.py` | `pytestmark = pytest.mark.integration`; deselected by `addopts = "-m 'not integration'"` |

### Scripts

| Script | Path | Imports `tg_mcp`? | Purpose |
|---|---|---|---|
| `login.py` | `scripts/login.py` | No | Interactive sign-in producing a `StringSession` string on stdout |

<!-- MEANING LAYER -->

### Purpose

A local stdio MCP server that exposes a deliberately narrow Telegram surface: read recent messages from channels passed per-call, and send digests to Saved Messages (or an explicit chat). The package is structured to keep the FastMCP wiring (`server.py`) thin and the tool logic (`tools.py`) directly testable without launching a JSON-RPC transport. The split between `client.py` (Telethon lifecycle + error translation + retry policy) and `tools.py` (tool semantics) exists so that unit tests can replace the Telethon client wholesale via the `fake_client` fixture without monkey-patching individual methods.

The server is deliberately **not** responsible for: persisting which channels matter (no whitelist anywhere — see ADR-0001), formatting incoming text on the caller's behalf (see ADR-0003), or any destructive Telegram operation. The boundary is enforced by what is wired into `mcp.tool(...)` in `server.py` — adding a destructive tool requires editing that file.

### Data flow

**Read path (`search_channels` / `get_recent`).**

1. MCP host sends a JSON-RPC `tools/call` over stdin.
2. FastMCP dispatches to the registered coroutine in `tools.py` via `_CallLoggingMiddleware.on_call_tool`, which logs `tool_call name=… arg_keys=…` (values are not logged; `send_to_self.text` content never reaches the log).
3. `tools.search_channels` / `tools.get_recent` call `client.get_client()` — first call connects Telethon lazily under `_client_lock`; subsequent calls reuse the singleton.
4. For each `channel` in the call, `client.resolve_channel` calls `TelegramClient.get_entity` and translates Telethon errors (`UsernameNotOccupiedError`, `ChannelPrivateError`, `UsernameInvalidError`, plain `ValueError`) into `ChannelResolutionError(code=…)`.
5. `tools._collect_channel_messages` wraps `client.iter_messages` with `client.with_flood_retry`. The `since_dt` cutoff is applied client-side by breaking the async loop when `raw.date < since_dt` (Telethon's `offset_date` is intentionally **not** passed — see Gotchas).
6. Per-channel `ChannelResolutionError` becomes an `ErrorEntry` in `items`; `FloodLimitExceeded` becomes both an `ErrorEntry` with `error="flood_wait_exceeded"` and sets `partial=True`. The read continues to the next channel.
7. Result is a `ReadResult` whose `items` is a mixed list. Order matches input channel order.

**Send path (`send_to_self`).**

1. If `tag` is given, `formatting.prepend_tag` adds an escaped `#<tag>` first line + blank line. Body is not escaped.
2. `formatting.split_for_telegram` chunks to the 4096-character limit via paragraph → sentence → hard-character cascade.
3. Each chunk is sent with `parse_mode="MarkdownV2"`, wrapped in `client.with_flood_retry`. On a second consecutive `FloodWaitError` mid-batch, sending stops and `partial=True`; ids already accepted by Telegram stay in `message_ids`.
4. `link` is populated only when `chat` is `"@username"`; `"me"` and numeric ids yield `link=None`.

**Server lifecycle.**

Importing `tg_mcp.server` runs `_route_fastmcp_logs_to_file()` once, immediately after `from fastmcp import FastMCP`, which strips FastMCP's own `RichHandler` and re-enables `propagate=True` so its logs flow through whatever root file handler is later attached (see ADR-0002). `main()` then loads `.env`, configures the rotating file logger via `setup_logging()`, and starts `mcp.run(transport="stdio", show_banner=False)`. The `_lifespan` async context calls `client.shutdown()` on stop, which disconnects the Telethon singleton.

### Gotchas

- **`with_flood_retry` requires a coroutine factory, not a coroutine.** The function calls `factory()` twice on flood. Passing an already-awaited coroutine would raise on the retry. Callers in `tools.py` define local `async def factory(...)` closures.
- **`since_dt` is enforced client-side by `tools._collect_channel_messages`**, not by Telethon's `offset_date` kwarg. The current code passes `limit=…, search=…` to `iter_messages` and breaks the loop when `raw.date < since_dt`. Changing this to push `offset_date` into Telethon would alter the semantics of `limit_per_channel` (Telethon counts post-filter).
- **`client.get_client` raises `RuntimeError` if credentials are missing or the session is unauthorised.** Tools propagate this. The regression test `tests/test_server_stdio.py` deliberately starts the server with placeholder credentials and immediate EOF so that `get_client` is **never** called — the boot path must succeed without valid credentials so prompts can register the server before signing in.
- **Repeated `setup_logging()` calls are idempotent.** All handlers are removed before the new `RotatingFileHandler` is attached. This matters for test isolation and re-entry into `main()`.
- **`_route_fastmcp_logs_to_file` runs at module-import time of `tg_mcp.server`**, not from `main()`. The call sits between the `from fastmcp import FastMCP` import and the `mcp = FastMCP(...)` construction — i.e. after FastMCP's logger has been created (so the strip has something to remove) but before any FastMCP-internal logging fires. Putting it at import time ensures any in-process entry path (`python -m tg_mcp.server`, direct `import tg_mcp.server; mcp.run()`, the stdio integration test in `tests/test_server_stdio.py`) inherits the clean configuration without depending on whether `main()` was called. See ADR-0002.
- **`get_client` disconnects the previous singleton before replacing it.** If the cached client is present but `is_connected()` is False (Telethon dropped the link mid-session), the new code in `get_client` calls `await prev.disconnect()` before constructing a new `TelegramClient`. Skipping that step leaks Telethon's background sender/keepalive tasks on every reconnect — visible only in long-running sessions with transient network drops.
- **`formatting.split_for_telegram` preserves inter-sentence whitespace.** Sentence-level splitting goes through `_split_keeping_separators` + `_pack_preserving`, which retain each segment's trailing separator. The earlier `re.split` + `" ".join` flow collapsed mid-paragraph newlines to single spaces; the new path leaves them intact. The character-level `_hard_split` additionally checks for a trailing odd-length run of backslashes on each chunk boundary and shifts a dangling `\` to the next chunk so neither side hands Telegram's MarkdownV2 parser a broken escape pair.
- **`tools._send_link` lowercases the `@username` segment.** Telegram usernames are case-insensitive and Telethon canonicalises `entity.username` to lowercase. `_build_message_link` (read-side, uses the resolved entity) already produced lowercase URLs; `_send_link` (send-side, uses the caller's literal string) now does the same, so a send to `"@FooBar"` and a subsequent read of the same channel produce equal link strings.
- **`send_to_self` treats `text` as already-valid MarkdownV2.** This is deliberate (see ADR-0003). A caller mistake surfaces as Telegram's `MarkdownV2 parse error` returned through the Telethon exception path.
- **No whitelist exists in env, code, or persistent state** (see ADR-0001). Every call carries its own `channels` / `channel` argument. The server does not remember between calls.
- **The integration test is deselected by default** via `pyproject.toml`'s `addopts = "-m 'not integration'"`. Run with `uv run pytest -m integration` and a populated `.env` to exercise live MTProto.

_Meaning layer last reviewed: 2026-05-11 against structure hash 8a1f912f147221edae2a564438abf87e_

<!-- /MEANING LAYER -->
