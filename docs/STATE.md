# STATE — telegram_mcp

_Last updated: 2026-05-11 14:47_

## Current

**Active branch:** `claude/check-project-status-yc8Se`.
**In progress:** Final `docs:` commit on this branch — landing the post-review CODEMAP/ADR refresh (this commit). After it lands the branch is ready to push and merge.
**Recently shipped:** Pre-merge triad complete. `b595297` (`fix:`) applied all P1 and P2 findings from `code-reviewer` (required `since`, leak-free reconnect in `get_client`, whitespace-preserving sentence splitter, MarkdownV2 escape-pair guard in `_hard_split`, lowercase `@username` in `_send_link`, FastMCP silencer hoisted to module-import time, `fastmcp>=3.0,<4` pin, `--out` flag on `scripts/login.py`). `9c81b09` (`test:`) added 26 new tests (middleware unit tests, stdio full-protocol exchange, edge cases for search/send/formatting/client/logging). 109 tests pass + 1 deselected (was 82 + 1 before the triad).
**Blocked / waiting on:** nothing.
**Next up:** commit the docs refresh, push `claude/check-project-status-yc8Se`, open a PR, squash-merge into `main` via `/merge-pr`.

### Notes

- The hard invariants previously tracked in this file are codified as ADRs:
  - No channel whitelist anywhere — see [ADR-0001](ADR/0001-no-channel-whitelist-in-server.md).
  - No stdout writes from server code (stdio transport invariant) — see [ADR-0002](ADR/0002-stdio-transport-no-stdout-writes.md). Regression guards: `tests/test_server_stdio.py` (two tests — immediate-EOF and full-protocol exchange).
  - `send_to_self` treats `text` as already-valid MarkdownV2 (locked option (a)) — see [ADR-0003](ADR/0003-markdownv2-caller-contract.md). Reversal to full-escape is a one-line change if practice proves it wrong.
  - `search_channels.since` is required (no `Optional[str] = None` default) — see [ADR-0004](ADR/0004-search-channels-since-required.md). Escape hatch: a wide window like `"36500d"`.
- Module overview: [docs/CODEMAPS/tg_mcp.md](CODEMAPS/tg_mcp.md).
- Open items from the plan that this branch did **not** resolve and are not yet promoted to ADRs:
  - `link` field semantics for non-public chats: implemented as documented (public `@username` → `https://t.me/<username>/<id>`; `"me"` and numeric chat_id → `None`). If a v2 caller needs a `tg://` deeplink for joined private chats, that becomes its own ADR at the moment of the decision.

## History

### 2026-05-11 00:00

**In progress:** Pre-merge triad on `claude/check-project-status-yc8Se` — `test-writer`, `code-reviewer`, and `document-agent` running in parallel before push + PR + merge.
**Recently shipped:** Slices 1–8 of the v1 plan, in eight sequential commits from `783fe3d` (bootstrap) through `737c2bf` (full README + integration stub). 82 tests pass; the integration test is deselected by `addopts`. Manual `python -m tg_mcp.server </dev/null` produces 0 bytes on stdout and stderr.
**Blocked / waiting on:** nothing.
**Next up:** address triad findings (if any), push the branch, open a PR, squash-merge into `main` via `/merge-pr`.

#### Notes (historical)

- The hard invariants previously tracked in this file have been codified as ADRs and are no longer carried as inline notes:
  - No channel whitelist anywhere — see [ADR-0001](ADR/0001-no-channel-whitelist-in-server.md).
  - No stdout writes from server code (stdio transport invariant) — see [ADR-0002](ADR/0002-stdio-transport-no-stdout-writes.md). Regression guard: `tests/test_server_stdio.py`.
  - `send_to_self` treats `text` as already-valid MarkdownV2 (locked option (a)) — see [ADR-0003](ADR/0003-markdownv2-caller-contract.md). Reversal to full-escape is a one-line change if practice proves it wrong.
- Module overview: [docs/CODEMAPS/tg_mcp.md](CODEMAPS/tg_mcp.md).
- Open items from the plan that this branch did **not** resolve and are not yet promoted to ADRs:
  - `link` field semantics for non-public chats: implemented as documented (public `@username` → `https://t.me/<username>/<id>`; `"me"` and numeric chat_id → `None`). If a v2 caller needs a `tg://` deeplink for joined private chats, that becomes its own ADR at the moment of the decision.

### 2026-05-09 00:00

> ✅ **Merged 2026-05-09:** `42ee10e` — chore: bootstrap project with CLAUDE.md, plan, and STATE.md (PR #3)

**Project status:** Plan phase complete — implementation pending.
**In progress:** none (plan approved; implementation has not started).
**Recently shipped:** nothing yet — greenfield repo.
**Blocked / waiting on:** nothing.
**Next up:** implement Slice 1 (skeleton) from the plan — `pyproject.toml` with deps (`telethon`, `fastmcp`, `pydantic>=2`, `python-dotenv`; dev: `pytest`, `pytest-asyncio`), `.gitignore`, `.env.example` with five `TG_*` vars, empty `src/tg_mcp/__init__.py`, README skeleton. Done-when: `uv sync` works and `python -c "import tg_mcp"` succeeds.

#### Notes (historical)

- **Just decided (locked with user).** Stack: FastMCP (decorator API) + uv + Python 3.11+ + Telethon + pydantic v2. Decomposition: 8 sequential slices (skeleton → models/formatting → logging → Telethon wrapper → tools → server → login script → README). Slices have linear dependencies; no parallel sub-agent dispatch planned.
- **plan-reviewer outcome.** Engineering mode, APPROVED — 0 blockers, 3 warnings. All 4 fixes applied to the plan before implementation start.
- **Hard invariants (from `CLAUDE.md`) — must hold in every slice.**
  - No channel whitelist in code, env, or persistent state — channels passed per-call only.
  - No stdout writes from server code — stdio is the MCP transport. All logs to rotating file (default `~/.local/state/tg-mcp/server.log`). Slice 6 includes an automated stdout-silence test (`tests/test_server_stdio.py`).
  - No destructive Telegram operations — read + send-to-self only.
  - Server never queries channels not in the current call's `channels`/`channel` arg.
  - Server never sends to chats other than the explicit `chat` arg of `send_to_self` (default `"me"`).
- **Open risks carried from the plan (not yet resolved in code).**
  - MarkdownV2 caller contract for `send_to_self`: option (a) locked — caller passes already-valid MarkdownV2, server only escapes the tag. README must document this so prompts do not double-escape. Switching to option (b) is a one-line change if practice proves option (a) wrong.
  - `link` field semantics for non-public chats: public channel → `https://t.me/<username>/<id>`; `chat="me"` → `None`; numeric `chat_id` → `None` for v1 (no robust public form). Documented in plan; will be re-stated in `Message`/`SendResult` model docstrings.
- **No ADR or CODEMAP exists yet.** Both will be created by `document-agent` in the pre-merge triad once implementation lands. First ADR target: the "no whitelist in server" invariant.

Project bootstrapped. Repo contains only `CLAUDE.md` and the approved plan at `docs/plans/setup-project-workflow-hrLJK.md`.
