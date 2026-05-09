# STATE — telegram_mcp

_Last updated: 2026-05-09 00:00_

## Current

**Active branch:** `claude/setup-project-workflow-hrLJK`
**Project status:** Plan phase complete — implementation pending.
**In progress:** none (plan approved; implementation has not started).
**Recently shipped:** nothing yet — greenfield repo.
**Blocked / waiting on:** nothing.
**Next up:** implement Slice 1 (skeleton) from the plan — `pyproject.toml` with deps (`telethon`, `fastmcp`, `pydantic>=2`, `python-dotenv`; dev: `pytest`, `pytest-asyncio`), `.gitignore`, `.env.example` with five `TG_*` vars, empty `src/tg_mcp/__init__.py`, README skeleton. Done-when: `uv sync` works and `python -c "import tg_mcp"` succeeds.

### Notes

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

## History

### 2026-05-09 00:00
Project bootstrapped. Repo contains only `CLAUDE.md` and the approved plan at `docs/plans/setup-project-workflow-hrLJK.md`.
