# ADR-0004: `search_channels.since` is a required argument

**Status:** Accepted
**Date:** 2026-05-11
**Scope:** `src/tg_mcp/tools.py` (`search_channels`), `README.md`,
`tests/test_search.py`

## Context

`tools.search_channels(channels, since, query, limit_per_channel)`
returns recent messages across one or more channels. The intent of the
tool, captured in the spec and the README from the start, is that every
batch query carries a time cutoff — callers should be requesting "what
happened since `7d` ago", not "give me everything".

The pre-merge code review found that the original signature exposed
`since: Optional[str] = None`. With the default, a caller (a prompt, an
LLM constructing the call, a future scripted job) could omit the
argument and silently request the full history of a channel. For a
moderately busy channel this is several megabytes of irrelevant
messages, fetched only to be discarded once `limit_per_channel` slices
the tail — and worse, a flood-wait trap on the way there. The README
documented "required cutoff", but the signature did not enforce it.

The asymmetry is the usual one: the safe behaviour is one extra word at
the call site (`since="36500d"` if you really want effectively no
cutoff); the unsafe behaviour is a flood wait, an oversized response, or
both, with no way to recover the cost.

## Decision

`search_channels.since` is mandatory. The Python signature has no
default; FastMCP exposes the argument with `"required": ["..., "since",
...]` in the tool's JSON schema, which the MCP host enforces at the
protocol level. Callers that genuinely want no cutoff pass an explicit
wide window — the README recommends `"36500d"` (~100 years).

`parse_since` rejects empty strings and unknown formats with `ValueError`,
so `since=""` is not a back door to the old behaviour.

The mirror tool `get_recent(channel, limit=30)` has **no** time cutoff
by design: it is the "give me the last N messages, full stop" surface,
bounded by `limit` rather than time. The two tools cover the two
intents explicitly; there is no third option of "no bound at all".

## Consequences

- Existing callers that omitted `since` get an error at protocol level
  ("Missing required argument") instead of an unbounded fetch. This is
  the desired failure mode — the diagnostic is immediate and the fix
  is mechanical.
- The README documents the wide-window escape hatch (`since="36500d"`)
  next to the `search_channels` reference so the option is discoverable
  without spelunking through tests.
- `tests/test_search.py` no longer has a `since=None` happy-path test;
  it now has `test_wide_since_window_includes_ancient_messages` which exercises the
  same code path (no real cutoff) by passing a wide window.
- The verification surface for "the tool actually advertises this as
  required" lives in `tests/test_server_stdio.py::test_full_protocol_exchange_keeps_stdio_clean`,
  which inspects the live `tools/list` JSON schema and asserts
  `"since" in inputSchema.required`. A regression that re-introduces a
  default would flip that assertion.

## Alternatives considered

- **Keep `since: Optional[str] = None`, document "required" only in the
  docstring.** Rejected — this was the original code. Documentation in
  prose loses to a default in code every time, especially when the
  caller is an LLM reading the schema rather than the docstring.
- **Default `since` to a fixed conservative window (e.g. `"7d"`).**
  Rejected — a silent default masks intent at the call site. A caller
  that wanted 24h and got 7d would have no easy way to notice. Making
  the value mandatory forces the choice to be visible at the call.
- **Add a separate `search_channels_all_history` tool for the rare
  no-cutoff use case.** Rejected as premature — the wide-window escape
  hatch covers the use case without inflating the tool surface. The MCP
  tool surface is deliberately small (3 tools); adding a fourth one
  whose only purpose is to bypass a safety property of the third is the
  wrong shape.

## References

- `src/tg_mcp/tools.py` — `search_channels` signature and docstring.
- `src/tg_mcp/client.py` — `parse_since` rejects empty input.
- `README.md` — usage examples and the `"36500d"` escape-hatch note.
- `tests/test_search.py` — `test_wide_since_window_includes_ancient_messages`.
- `tests/test_server_stdio.py` — `test_full_protocol_exchange_keeps_stdio_clean`
  asserts `since` is in the live JSON schema's `required` list.
- ADR-0001 (no whitelist) — same family of decisions: the server
  refuses to silently assume what the caller meant.
