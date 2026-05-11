# Architectural Decision Records

This directory holds ADRs for the `tg-mcp` server. ADRs are immutable once
accepted; supersede by writing a new ADR and updating the old one's status
line to `Superseded by ADR-XXXX`.

## Index

| ID | Title | Status | Date |
|---|---|---|---|
| [ADR-0001](0001-no-channel-whitelist-in-server.md) | No channel whitelist in server | Accepted | 2026-05-11 |
| [ADR-0002](0002-stdio-transport-no-stdout-writes.md) | stdio transport implies no stdout writes from server code | Accepted | 2026-05-11 |
| [ADR-0003](0003-markdownv2-caller-contract.md) | `send_to_self` treats `text` as already-valid MarkdownV2 | Accepted | 2026-05-11 |
| [ADR-0004](0004-search-channels-since-required.md) | `search_channels.since` is a required argument | Accepted | 2026-05-11 |
