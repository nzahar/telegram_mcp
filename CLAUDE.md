# Telegram MCP — project instructions

## Project type

- `default_agent_mode: engineering`
- `state_owner: document-agent`

This is an engineering project (no `notebooks/`, no ML/research workflow). Sub-agents that support modes (`plan-reviewer`, `code-reviewer`) must use the **engineering** rubric. `docs/STATE.md` is owned by `document-agent`.

## Stack

- Python 3.11+
- Telethon (MTProto client)
- FastMCP (decorator-based MCP SDK, stdio transport)
- uv for dependency management
- pytest for tests

## Hard constraints (from spec)

- **No channel whitelist** anywhere in code, env, or persistent state. Channels are passed as arguments on every call. Whitelist control belongs to the prompt side (Cowork scheduled task / ad-hoc).
- **No stdout writes from server code.** stdout is the MCP transport — any print/log to stdout corrupts the protocol. All logging goes to a rotating file (default `~/.local/state/tg-mcp/server.log`).
- **No destructive Telegram operations.** Server exposes read + send-to-self only. No delete, no leave-channel, no invite, no ban, no edit-of-others.
- **Server never queries channels not passed explicitly** in the current call's `channels` / `channel` argument.
- **Server never sends to chats other than the explicit `chat` argument** of `send_to_self` (default `"me"`).

## Conventions

- Conventional commits in English (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`).
- Secrets via `.env` (gitignored); `.env.example` is committed.
- Plans live at `docs/plans/<branch-slug>.md`.
- ADRs at `docs/ADR/`, CODEMAPS at `docs/CODEMAPS/` — created via `document-agent` when structural decisions land.

## STATE.md conventions

- **Do not record the active branch in `docs/STATE.md`.** Cloud-runtime sessions create ephemeral branches (`claude/<slug>-<hash>`) that are deleted on merge — recording them in committed docs guarantees staleness within hours. Branch state belongs to git, not to STATE.md. `document-agent` must skip the "Active branch" field when refreshing STATE.md for this project. Other STATE.md fields (project status, in-progress work, next-up, blocked, notes, history) remain.
