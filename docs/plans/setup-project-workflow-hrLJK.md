# Plan: Telegram MCP server (initial implementation)

Branch: `claude/setup-project-workflow-hrLJK`
Spec source: `f23d925f-tgmcpspec.md` (uploaded by user)
Mode: engineering

## 1. Context

Greenfield repo. Goal — local stdio MCP server in Python that:

1. Reads messages from public Telegram channels on demand (via three tools).
2. Sends digests to Saved Messages or an explicit chat.

The whitelist of channels is **not** part of the server's state. It lives in the prompt (Cowork scheduled task / ad-hoc). The server only acts on what each call passes in.

This plan covers the first end-to-end working version: project skeleton, Telethon wrapper, FastMCP server with three tools, formatting + splitting, login helper, unit tests, README, and Cowork integration notes.

No ADR or CODEMAP exists yet — they will be created by `document-agent` in the pre-merge triad once the implementation lands. The plan therefore does not reference any existing ADR/invariants (none to respect or supersede).

## 2. Decisions (locked with the user)

| Decision | Choice | Reason |
|---|---|---|
| MCP SDK | **FastMCP** | Decorator API minimises boilerplate for three tools; spec allows it. |
| Package manager | **uv** | Spec already references `uv sync`; lock file + speed. |
| Python | **3.11+** | Per spec; matches modern Telethon and FastMCP. |
| Auth model | Session string in env var (`TG_SESSION_STRING`) | Per spec. No on-disk session files. |
| Logging | Python `logging` + `RotatingFileHandler`, never stdout | stdio transport occupies stdout. |
| Pydantic version | v2 | FastMCP uses pydantic v2; align. |
| Telethon client lifecycle | Module-level lazy singleton, connected on first tool call, disconnected on shutdown | Per spec ("lazy-init"). |
| Long-message splitting | Split by paragraph (`\n\n`); if a paragraph exceeds 4096, split by sentence; if a sentence still exceeds, hard-split by character | Spec says "by paragraphs" but doesn't cover degenerate cases — hard-split is the fallback. |
| `since` parsing | Accept `Nd` / `Nh` / `Nm` and ISO-8601 (date or datetime) | Per spec examples: `7d`, `24h`, `3h`. |
| MarkdownV2 escaping | Escape the documented set: `_*[]()~`>#+-=|{}.!` plus `\` | Telegram MarkdownV2 spec. |
| Tag formatting in `send_to_self` | First line is `#<tag>` exactly (no extra prefix), then blank line, then body | Per spec. Tag content escaped MarkdownV2-safe. |
| Chat resolution | `"me"` → Saved Messages; `@username` → public; numeric → chat_id (passed to Telethon as int) | Per spec. |
| FloodWait policy | One retry after the wait Telethon reports; on second flood — return `partial: true` with what we have | Per spec. |
| Default `parse_mode` for `send_to_self` | `"MarkdownV2"` | Spec says it supports MarkdownV2. |

## 3. Architecture

```
src/tg_mcp/
  __init__.py
  server.py        # FastMCP entrypoint: tool registration, lifespan, logging setup
  client.py        # Telethon singleton + lazy connect/disconnect, channel resolution, since-parsing, FloodWait retry
  tools.py         # Pure-ish tool implementations: search_channels, get_recent, send_to_self (depends on client.py)
  models.py        # Pydantic v2: Message, ErrorEntry, SendResult
  formatting.py    # MarkdownV2 escape, split-by-paragraph/sentence/char, tag prepending
  logging_setup.py # Rotating file handler config (1 MB, 5 files, INFO default, DEBUG via TG_LOG_LEVEL)
scripts/
  login.py         # Interactive: prompts phone + code, prints session string to stdout, exits
tests/
  conftest.py      # Async pytest config, mock Telethon factory
  test_search.py   # search_channels: happy path, broken channel returns ErrorEntry, FloodWait retry
  test_get_recent.py
  test_send.py     # MarkdownV2 escape, paragraph split, tag, single-vs-multi message_id
  test_since_parsing.py
  test_integration.py  # @pytest.mark.integration — skipped in default run
pyproject.toml
.env.example
.gitignore
README.md
```

**Why split `tools.py` from `server.py`:** keeps tool logic testable without spinning up FastMCP. `server.py` becomes thin: import tools, register, run. Tests can import `tools.search_channels(...)` directly with a mocked client.

## 4. Decomposition (slices, in order)

Each slice is a single logical chunk. Implement sequentially — they have linear dependencies. No parallel sub-agent dispatch needed (project is small).

### Slice 1 — Skeleton
- `pyproject.toml` (project name, deps: `telethon`, `fastmcp`, `pydantic>=2`, `python-dotenv`; dev: `pytest`, `pytest-asyncio`)
- `.gitignore` (Python defaults + `.env`, `.venv/`, `*.session*`, `__pycache__/`)
- `.env.example` (five `TG_*` vars: `TG_API_ID`, `TG_API_HASH`, `TG_SESSION_STRING`, `TG_LOG_PATH`, `TG_LOG_LEVEL=INFO`; no real values)
- `src/tg_mcp/__init__.py` (empty / version)
- `README.md` skeleton (sections only, filled in slice 8)

**Done when:** `uv sync` works, `python -c "import tg_mcp"` works.

### Slice 2 — Models + formatting (pure logic, no Telethon)
- `models.py`: `Message`, `ErrorEntry`, `SendResult` pydantic models
- `formatting.py`: `escape_md_v2(text)`, `split_for_telegram(text, limit=4096)`, `prepend_tag(text, tag)`
- Tests: `test_send.py` formatting cases (escape correctness, paragraph split, sentence fallback, char fallback, tag prepending)

**Done when:** `pytest tests/test_send.py` green; covers escape table, three split levels, tag with/without `#`.

### Slice 3 — Logging
- `logging_setup.py`: `setup_logging()` configures root logger with `RotatingFileHandler` (1 MB × 5 files), level from `TG_LOG_LEVEL` env (default INFO), path from `TG_LOG_PATH` (default `~/.local/state/tg-mcp/server.log`), creates parent dir if missing
- **No StreamHandler.** Asserted by test: capture stdout/stderr during `setup_logging()` + `logger.info("test")`, expect both empty.

**Done when:** test verifies file is written, stdout/stderr stay empty.

### Slice 4 — Telethon wrapper
- `client.py`:
  - Module-level `_client: TelegramClient | None`
  - `async def get_client()` — lazy connect using session string from env, returns singleton
  - `async def shutdown()` — disconnect if connected
  - `parse_since(s: str) -> datetime` — handles `Nd`/`Nh`/`Nm` (UTC now-relative) and ISO-8601
  - `async def resolve_channel(client, ref: str | int)` — wraps `client.get_entity` with friendly error mapping (UsernameNotOccupied, ChannelPrivate, ValueError → ErrorEntry)
  - `async def with_flood_retry(coro_factory, log)` — runs once; on `FloodWaitError` waits exact reported seconds, runs once more; on second flood raises a sentinel handled by tools to mark `partial`
- Tests: `test_since_parsing.py` (happy + bad inputs), `test_search.py` partially (uses mocked client to validate retry path)

**Done when:** since-parsing covered; `with_flood_retry` test asserts one wait-and-retry then surface.

### Slice 5 — Tools
- `tools.py`:
  - `search_channels(channels, query, since, limit_per_channel=50)` — for each channel: resolve → iterate `client.iter_messages(entity, limit=limit_per_channel, search=query or None, offset_date=since_dt)` → map to `Message`. Errors per-channel become `ErrorEntry` items in the same list. Wrap calls with `with_flood_retry`.
  - `get_recent(channel, limit=30)` — single-channel variant; same error handling.
  - `send_to_self(text, chat="me", tag=None)` — apply tag, escape MarkdownV2 only on tag (caller-provided text is treated as already MarkdownV2 — per spec wording "supports MarkdownV2"; document this in README), split if needed, send each piece, return `SendResult` with one or many `message_id`s. `link` rules for `SendResult`:
    - `chat="me"` → `link=None` (Saved Messages have no public link)
    - `chat="@username"` (public) → `link="https://t.me/<username>/<first_message_id>"`
    - numeric chat_id → `link=None` for v1 (no robust public form)
- Tests: `test_search.py` full (mock iter_messages with synthetic messages; assert ErrorEntry for bad channel, partial flag after double flood), `test_get_recent.py`, `test_send.py` send-side (mock `client.send_message`, verify split into N calls).

**Done when:** all unit tests in `tests/` (except `integration`) green; coverage of three tools' happy paths + each spec-listed edge case.

### Slice 6 — Server
- `server.py`:
  - Read env (`python-dotenv` for local dev), call `setup_logging()`
  - Create `FastMCP("tg-mcp")`
  - Register three tools with explicit pydantic-typed signatures (FastMCP infers schema from type hints + docstring)
  - Register lifespan that calls `client.shutdown()` on stop
  - Per-call logging middleware: log tool name, arg keys (omit `text` for `send_to_self`), elapsed ms, response size
  - `if __name__ == "__main__": mcp.run()` — stdio transport
- **Automated stdout-silence test.** Add `tests/test_server_stdio.py`: launches `python -m tg_mcp.server` via `subprocess.run([...], input=b"", capture_output=True, timeout=2)` (server exits on EOF or is killed by timeout), then `assert result.stdout == b""`. This guards the "no stdout" invariant against accidental `print()` regressions — without an automated test, regression surfaces only inside Cowork when the MCP protocol breaks.

**Done when:** server starts and logs to file; `test_server_stdio.py` passes (stdout empty); manual `python -m tg_mcp.server` blocks on stdin without crashing.

### Slice 7 — Login script
- `scripts/login.py`: standalone, no dependency on `tg_mcp` package. Reads `TG_API_ID`/`TG_API_HASH` from env or prompts. Uses `TelegramClient(StringSession(), ...)`, signs in interactively (phone + code, optional 2FA password), prints session string to stdout, **does not write any session file** (`StringSession()` keeps it in memory).
- Documented in README with the warning that this is the *only* place the session string is exposed.

**Done when:** `python scripts/login.py --help` works; manual run flow documented (cannot integration-test in CI).

### Slice 8 — README + Cowork wiring
- README sections: install, login, run for debugging, register in Cowork (with the JSON block from spec), troubleshooting (the four error cases from spec), security note (whitelist lives in prompt, not server).

**Done when:** README is self-contained for a fresh user with the spec in hand.

## 5. Edge-case → test mapping

| Spec edge case | Test |
|---|---|
| Channel not found / private / deleted → `ErrorEntry`, no exception | `test_search.py::test_broken_channel_returns_error_entry` |
| `FloodWaitError` once → wait + retry once | `test_search.py::test_flood_wait_retried_once` |
| `FloodWaitError` twice → `partial: true` | `test_search.py::test_double_flood_marks_partial` |
| `text` > 4096 → split by paragraph | `test_send.py::test_split_by_paragraph` |
| Single paragraph > 4096 → split by sentence | `test_send.py::test_split_by_sentence_fallback` |
| Single sentence > 4096 → hard-split by char | `test_send.py::test_hard_split_fallback` |
| Lazy-init client | `test_search.py::test_client_initialised_once` |
| `since` parsing variants | `test_since_parsing.py` parametrised |
| `tag` with and without leading `#` → exactly one `#` | `test_send.py::test_tag_normalised` |
| Caller-provided MarkdownV2 body passes through un-escaped (contract (a)) | `test_send.py::test_markdown_v2_passthrough` |
| Server writes nothing to stdout when running as `python -m tg_mcp.server` | `test_server_stdio.py::test_stdout_is_silent` |

## 6. Verification plan

Before declaring the slice complete:

- `uv run pytest -q` — all non-integration tests pass.
- `uv run python -m tg_mcp.server` — process starts, blocks on stdin, no stdout output (verify with `python -m tg_mcp.server </dev/null 2>err.log`; expect no stdout, error log contains a graceful EOF or stays minimal).
- `uv run python scripts/login.py --help` — exits 0.
- `cat ~/.local/state/tg-mcp/server.log` after a unit test run touching logging — file exists, contains entries.
- (Manual, not CI) Integration test marked `@pytest.mark.integration` — left documented; run only when user has session string available locally.

## 7. Out of scope (explicitly NOT in this branch)

- Channel discovery / suggestions
- Saving channel whitelist anywhere
- Media download (only `text`, `link`, `views` per spec)
- Reply-to / forward / edit operations
- Subscribing to live updates (only on-demand pull)
- Any second chat target beyond what `send_to_self` accepts as `chat` argument
- ADR / CODEMAPS files — those are created by `document-agent` in pre-merge, not in this slice plan

## 8. Risks / open items

- **MarkdownV2 caller contract.** Spec says `send_to_self` "supports MarkdownV2". Two readings: (a) caller passes already-valid MarkdownV2 — server only escapes the tag; (b) server escapes everything. Locked: option (a). README will document this so prompts don't double-escape. If proven wrong in practice, switch is one-line.
- **`link` field on `Message`.** Public channels: `https://t.me/<username>/<id>`. Private (joined-as-user): no clean public URL — return `None` (or `tg://...` deeplink? — left as `None` for v1, documented).
- **`views` field.** Available only for channel messages (not group). For groups: `None`. Documented in `Message` model.
- **Session string in env.** Standard Telethon practice; the actual secret-handling boundary is the user's `.env` and Cowork connector config. README will warn against committing it.

## 9. Workflow checkpoints

- [ ] User approves this plan
- [ ] `plan-reviewer` (engineering mode) — background — six-dimension report shown to user
- [ ] User decides which findings (if any) to address
- [ ] Implement slices 1–8 sequentially, committing after each (commits are local; no push without explicit user request)
- [ ] Pre-merge triad on user signal: `code-reviewer` (engineering), `test-writer`, `document-agent` (creates initial ADR for "no whitelist in server" invariant + CODEMAP for `tg_mcp/`) — three parallel background agents
- [ ] User merges via `/merge-pr`
