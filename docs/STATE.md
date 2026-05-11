# STATE — telegram_mcp

_Last updated: 2026-05-11 15:15_

## Current

> ✅ **Merged 2026-05-11:** `e9775f1` — feat: Telegram MCP server v1 (read + send-to-self over stdio) (#6)

**In progress / awaiting user action:** push `claude/check-project-status-yc8Se`, open a PR, squash-merge into `main` via `/merge-pr`. Claude does not push without explicit user command — the branch is otherwise complete.
**Recently shipped:** v1 implementation across 15 commits on `claude/check-project-status-yc8Se`. Three pre-merge triad passes (`test-writer`, `code-reviewer`, `document-agent`) all returned APPROVED on the current state. 138 tests passing + 1 deselected integration. Latest commit: `b1d99e9` (test+docs: pass-3 verification additions — adds five unit cases on `_build_message_link` after re-reading the file).
**Blocked / waiting on:** nothing.
**Next up:** Stage 2 — HTTP transport + remote deploy — per [docs/ROADMAP.md](ROADMAP.md). Locked: a dedicated Telegram account will be used for the deployed server (not a personal one). Open and to be settled in a spec session **before** the branch opens: hosting platform (Fly.io / Railway / Codespace+cloudflared / VPS), auth model (bearer token is the current candidate), CI/CD trigger (push-to-main vs tag vs manual), and whether `send_to_self` is exposed remotely or restricted to local stdio (read-only-on-deploy). Trigger: user signals readiness to start the branch.

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

### 2026-05-11 15:10

**Active branch:** `claude/check-project-status-yc8Se`.
**In progress:** Third-pass pre-push verification triad in flight. Second-pass triad findings landed in `de30c0f` (`fix:`), `6a3344b` (`test:`), `5e9a097` (`docs:`); third pass re-verifies the result. Test count corrected here (actual is 133 passed + 1 deselected). Branch is ready to push and merge once the third pass finishes.
**Recently shipped:** Second-pass triad addressed: `de30c0f` (`fix:`) made `scripts/login.py::_write_session_file` atomic via `mkstemp + os.replace`, narrowed `client.get_client` stale-cleanup catch to `(ConnectionError, OSError)` with `_log.warning(...)`, lowercased `_build_message_link` for symmetry with `_send_link`, fixed `search_channels` parameter order in README. `6a3344b` (`test:`) added 24 tests (109 → 133) covering the new TOCTOU/atomicity guards, the narrow-catch contract, the bare-`@` no-link case, sentence-splitter whitespace preservation, hard-split escape-pair defence, and `_route_fastmcp_logs_to_file` via the new `TestFastMCPLoggerStrip`. `5e9a097` (`docs:`) added `docs/SETUP.md` (operator setup memo) and fixed an ADR-0004 stale test reference. Earlier on the same branch: first-pass triad (`b595297`, `9c81b09`, `1e0153e`).
**Blocked / waiting on:** nothing.
**Next up:** push `claude/check-project-status-yc8Se`, open a PR, squash-merge into `main` via `/merge-pr`.

#### Notes (historical)

- The hard invariants previously tracked in this file are codified as ADRs:
  - No channel whitelist anywhere — see [ADR-0001](ADR/0001-no-channel-whitelist-in-server.md).
  - No stdout writes from server code (stdio transport invariant) — see [ADR-0002](ADR/0002-stdio-transport-no-stdout-writes.md). Regression guards: `tests/test_server_stdio.py` (two tests — immediate-EOF and full-protocol exchange).
  - `send_to_self` treats `text` as already-valid MarkdownV2 (locked option (a)) — see [ADR-0003](ADR/0003-markdownv2-caller-contract.md). Reversal to full-escape is a one-line change if practice proves it wrong.
  - `search_channels.since` is required (no `Optional[str] = None` default) — see [ADR-0004](ADR/0004-search-channels-since-required.md). Escape hatch: a wide window like `"36500d"`.
- Module overview: [docs/CODEMAPS/tg_mcp.md](CODEMAPS/tg_mcp.md).
- Open items from the plan that this branch did **not** resolve and are not yet promoted to ADRs:
  - `link` field semantics for non-public chats: implemented as documented (public `@username` → `https://t.me/<username>/<id>`; `"me"` and numeric chat_id → `None`). If a v2 caller needs a `tg://` deeplink for joined private chats, that becomes its own ADR at the moment of the decision.

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
