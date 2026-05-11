# ADR-0001: No channel whitelist in server

**Status:** Accepted
**Date:** 2026-05-11
**Scope:** `src/tg_mcp/`, `.env.example`, server configuration surface

## Context

The server reads messages from Telegram channels and sends digests on
demand. The natural temptation when building such a server is to bake in a
list of "channels this server is allowed to touch" — either as an env var
(`ALLOWED_CHANNELS=…`), a config file, or a persistent cache built up from
prior calls. Each option is plausible: it gives operators a place to put
defaults, and it lets the server reject calls for channels the deployer
did not bless.

We deliberately rejected all such forms.

The server is consumed by multiple callers — scheduled tasks in a Cowork
runtime, ad-hoc questions from a chat session, future MCP hosts. Each
caller carries its own notion of "channels I care about right now". A
news-digest cron at 09:00 covers one set of handles; an ad-hoc question
five minutes later covers a different set; a follow-up tomorrow covers a
third. Encoding any of these into the server forces the union into one
config that every caller must share — and the union grows monotonically,
because nobody wants to be the one who removed a channel.

## Decision

The server holds no list of channels. There is no `ALLOWED_CHANNELS` env
var, no on-disk allow-list, no in-memory cache built from prior calls.
Every tool call passes its own `channels` (or `channel`) argument, and the
server acts only on what that single call hands it. The whitelist policy —
"these are the handles my morning digest covers" — lives in the prompt
that invokes the tool, never in the server.

This is enforced by structure rather than by a check: `tools.py` only
iterates the argument it receives, and `client.resolve_channel` only
resolves what the caller passed. There is nowhere in the code to add a
channel that is not already in the call.

## Consequences

- Policy lives with the caller (prompt or scheduled job). A new digest
  topic is a new prompt, not a config push.
- The same deployed binary serves any caller — multi-tenant by default.
- The server cannot leak "which channels the deployer cares about"
  because it does not know.
- Auditing is straightforward: a log line per call lists which channels
  were touched, with no ambient state to reconcile against.
- The caller is responsible for any access control. A compromised or
  malicious prompt can ask the server to read any channel the session
  string can reach. The credential boundary is the session string, not
  a channel allow-list.
- Adding a whitelist later is a non-trivial reversal: it would require
  a new env var or config file, a check in every tool, and a story for
  how the union is composed across callers. Reverting this ADR should
  go through a superseding ADR.

## Alternatives considered

- **`ALLOWED_CHANNELS` env var.** Rejected: forces all callers to share
  one union, which only grows; harms multi-tenant deployments.
- **On-disk allow-list file the operator edits.** Rejected: same union
  problem plus a state file to keep in sync across machines.
- **In-memory cache built from observed calls.** Rejected: turns the
  server into a stateful component with no clear eviction story, and
  the cache contents would depend on call order — non-deterministic.

## References

- Project `CLAUDE.md` — hard constraints section ("No channel whitelist").
- `docs/CODEMAPS/tg_mcp.md` — Purpose section.
- `README.md` — Security section.
