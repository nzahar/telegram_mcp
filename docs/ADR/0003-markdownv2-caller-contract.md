# ADR-0003: `send_to_self` treats `text` as already-valid MarkdownV2

**Status:** Accepted
**Date:** 2026-05-11
**Scope:** `src/tg_mcp/tools.py::send_to_self`,
`src/tg_mcp/formatting.py::prepend_tag`, README "Tools" section

## Context

The `send_to_self` tool always sends with `parse_mode="MarkdownV2"`.
Telegram's MarkdownV2 grammar requires a specific set of characters
(``_*[]()~`>#+-=|{}.!\``) to be backslash-escaped wherever they do not
form valid markup. The spec says the tool "supports MarkdownV2", which
admits two readings:

- **(a) Caller produces valid MarkdownV2.** The server forwards `text`
  unchanged; the caller is responsible for any escaping it needs.
- **(b) Server escapes everything.** The tool treats `text` as plain
  characters and applies `escape_md_v2` before sending. No markup ever
  survives.

The prompts that drive this server are LLM-authored digests. A useful
digest has formatting — bold headings, italic asides, links to source
posts. Option (b) would force every prompt to render literal asterisks
instead of bold, defeating the purpose of MarkdownV2 in the first place.
Option (a) preserves formatting but moves correctness onto the caller:
a malformed escape (`*bold` without the closing `*`, an unescaped `.`)
surfaces as a Telegram parse error returned from the API.

## Decision

`send_to_self` treats `text` as already-valid MarkdownV2 and forwards
it to `TelegramClient.send_message` unchanged. The server only escapes
the optional `tag` parameter — `formatting.prepend_tag` calls
`escape_md_v2` on the normalised `#<tag>` so a caller passing
`tag="news.daily"` gets a working hashtag without thinking about the
period. Long-text splitting (`split_for_telegram`) operates on already-
escaped input and does not re-escape across split boundaries.

The README documents this contract explicitly in the `send_to_self`
section and in the troubleshooting entry for `MarkdownV2 parse error`.

## Consequences

- Prompts that produce digests get to use formatting naturally.
- A caller bug (unbalanced markup, unescaped special character) surfaces
  as a Telegram parse error returned through the Telethon exception
  path, not as silent plain-text output. The error message points at
  MarkdownV2.
- The server cannot detect a caller mistake before sending. Telegram is
  the only validator.
- Tag content is safe to pass loosely — the server normalises and
  escapes it for the caller.
- **Reversal cost is one line.** If experience shows that prompts
  consistently produce malformed MarkdownV2, switching to option (b)
  means adding `text = escape_md_v2(text)` at the top of `send_to_self`
  (and updating tests + README). The split logic does not need to
  change because `escape_md_v2` does not introduce paragraph or
  sentence boundaries. No schema change is involved.

## Alternatives considered

- **Option (b): server escapes everything.** Rejected for v1: kills
  formatting in digests, which is the primary use case. Kept as the
  fallback if option (a) proves wrong in practice — reversal is
  trivial.
- **Auto-detect markup and escape only when absent.** Rejected as
  underspecified: "is this markup?" is the parse problem we are trying
  to avoid; doing it half-correctly is worse than either extreme.
- **Two tools (`send_text` and `send_markdown`).** Rejected for v1 as
  surface bloat. Revisit if a non-MarkdownV2 use case appears.

## References

- Project `CLAUDE.md` — does not pin this choice; it is a v1 product
  decision.
- `docs/plans/setup-project-workflow-hrLJK.md` — section 8 "Risks /
  open items" recorded the choice as locked option (a).
- `src/tg_mcp/tools.py::send_to_self` — implementation.
- `src/tg_mcp/formatting.py::prepend_tag` — tag-only escape.
- `README.md` — Tools and Troubleshooting sections.
