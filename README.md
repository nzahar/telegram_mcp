# tg-mcp

Local stdio MCP server that lets an LLM read recent messages from public Telegram channels and send digests to your Saved Messages (or another chat you pass explicitly).

The server is intentionally minimal:

- **Read-only on channels.** Three tools — `search_channels`, `get_recent`, `send_to_self` — and nothing else. No delete, no edit-of-others, no leave, no invite.
- **No channel whitelist anywhere.** Every call passes the channels it wants to read. The list of "channels I care about" lives in the prompt (a Cowork scheduled task or an ad-hoc question), never in server config or persistent state.
- **stdio transport, file logging.** Nothing is written to stdout outside the JSON-RPC protocol. All diagnostics go to a rotating file log (`~/.local/state/tg-mcp/server.log` by default).

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- A Telegram account and API credentials from <https://my.telegram.org/apps>

## Install

```bash
git clone <this-repo> telegram_mcp
cd telegram_mcp
uv sync
```

`uv sync` creates `.venv/` and installs runtime + dev dependencies (`telethon`, `fastmcp`, `pydantic`, `python-dotenv`, plus `pytest` / `pytest-asyncio` for tests).

Copy the example env file:

```bash
cp .env.example .env
```

Fill in `TG_API_ID` and `TG_API_HASH` from <https://my.telegram.org/apps>. `TG_SESSION_STRING` is filled in by the next step.

## Login — generate a session string

The server authenticates via a Telethon `StringSession`. To produce one, run the interactive login script once:

```bash
uv run python scripts/login.py
```

You will be prompted for your phone (international format, e.g. `+12025550100`), the code Telegram sends to that number, and — if you have 2FA enabled — your account password.

Two output modes:

```bash
# default: print session string to stdout (good for one-shot interactive use)
uv run python scripts/login.py

# recommended: write directly to a file at mode 0600 — avoids leaks through
# `set -x`, shell history, and CI log capture.
uv run python scripts/login.py --out /tmp/tg-session.txt
```

Copy the resulting string into `.env` as `TG_SESSION_STRING`, then delete the temp file. The script keeps the session in memory only — no `*.session` file is ever written to disk.

**The session string is equivalent to your account password.** Anyone holding it can act as your Telegram account, including reading every chat and sending any message. Never commit `.env`. Never paste it into shared chat or pastebins. Avoid the default stdout mode in shells with `set -x` or under CI loggers — use `--out` there. `.gitignore` already excludes `.env` and `*.session*` files.

## Run

For local debugging, start the server attached to your terminal:

```bash
uv run python -m tg_mcp.server
```

The process reads `.env`, configures the rotating file logger, and then blocks on stdin waiting for MCP JSON-RPC requests. `Ctrl-C` to stop. Tail the log file in another terminal:

```bash
tail -f ~/.local/state/tg-mcp/server.log
```

If `~/.local/state/tg-mcp/server.log` is the wrong place for your machine, override with `TG_LOG_PATH=/path/to/file.log` in `.env`. Level defaults to `INFO`; set `TG_LOG_LEVEL=DEBUG` for verbose Telethon output.

## Register in Cowork (or any MCP host)

Add an entry to the host's MCP server config. The shape is the standard `mcpServers` block used by Claude Desktop, Cowork, and most MCP-capable clients:

```json
{
  "mcpServers": {
    "tg-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/telegram_mcp",
        "run",
        "python",
        "-m",
        "tg_mcp.server"
      ],
      "env": {
        "TG_API_ID": "1234567",
        "TG_API_HASH": "0123456789abcdef0123456789abcdef",
        "TG_SESSION_STRING": "1ApWapzMBu..."
      }
    }
  }
}
```

Replace `/absolute/path/to/telegram_mcp` with the repo path, and fill in your credentials. Restart the host after editing the config so the server is re-spawned.

## Tools

All tools return pydantic models that the host serialises as JSON.

### `search_channels(channels, since, query="", limit_per_channel=50) -> ReadResult`

Search for matching messages across multiple channels in a single call.

- `channels: list[str | int]` — channel references. `@username` for public channels, integer chat IDs for private ones already accessible to your account.
- `since: str` — **required** cutoff. Accepts `Nd` / `Nh` / `Nm` (e.g. `"7d"`, `"24h"`, `"30m"`) or an ISO-8601 date / datetime. Naive ISO is treated as UTC. The parameter is mandatory by design — pass a deliberately wide window (e.g. `"36500d"`) if you really want no cutoff. This prevents callers from accidentally requesting the full history of a channel.
- `query: str` — full-text query passed to Telegram's search. Pass `""` to fetch recent messages without filtering.
- `limit_per_channel: int` — cap per channel, default 50.

Returns `ReadResult(items, partial)` where `items` mixes `Message` and per-channel `ErrorEntry` records. `partial=True` if any channel was abandoned after a second consecutive `FloodWaitError`; previously delivered items from earlier channels are still present.

### `get_recent(channel, limit=30) -> ReadResult`

Single-channel variant — fetch the last N messages regardless of content. Same return shape as `search_channels`.

### `send_to_self(text, chat="me", tag=None) -> SendResult`

Send a digest to your own Saved Messages (or another chat you pass explicitly).

- `text: str` — message body. **The caller is responsible for valid MarkdownV2** (the server's `parse_mode` is always `MarkdownV2`). The server does not escape body content — prompts that build `*bold*` / `_italic_` / `[label](url)` get rendering. If a prompt is producing literal `*` characters by mistake, the prompt — not the server — should switch to plain text or pre-escape.
- `chat: str | int` — `"me"` (default) for Saved Messages, `"@username"` for a public chat you can post to, or a numeric chat ID.
- `tag: str | None` — optional hashtag prepended as the first line. Tag content is escaped for MarkdownV2 by the server. Leading `#` is normalised (one `#` regardless of whether you pass `news` or `#news`).

When `text` exceeds Telegram's 4096-character limit, the server splits it greedily: paragraphs first (split on blank lines), then sentences (split on `.`/`!`/`?`), then a hard character split as a last resort.

Returns `SendResult(chat, message_ids, link, partial)`:

- `message_ids` is one id per delivered chunk.
- `link` is `https://t.me/<username>/<first_id>` only when `chat` is `"@username"`. For `"me"` and numeric chat IDs it is `None`.
- `partial=True` if delivery stopped after a second `FloodWaitError`; the ids already delivered remain in `message_ids`.

## Troubleshooting

**`Channel not found` ErrorEntry.** The reference does not resolve. Common causes: typo in `@username`, the channel was deleted, or it is private and your account does not have access. For private chats you can only reach those that your signed-in account has already joined.

**`Channel private` ErrorEntry.** The handle resolves but your account is not a member.

**`Flood wait exceeded` ErrorEntry / `partial: true`.** Telegram rate-limited you twice in a row on this call. The server waited the seconds Telegram reported and retried once — the second `FloodWaitError` is surfaced rather than blocked on. Wait, then call again. If this is chronic, lower `limit_per_channel` or reduce call frequency.

**`MarkdownV2 parse error` returned by Telegram on `send_to_self`.** The body contained an unescaped special character (`_*[]()~\`>#+-=|{}.!` or `\`). Per the caller-contract above, the prompt must produce valid MarkdownV2. If you do not need formatting, the safest body is plain ASCII text or text already passed through a MarkdownV2 escape function on the caller side. Tag content does not need escaping — the server handles that.

**`TG_SESSION_STRING is present but not authorised`.** The session has been revoked (you logged out via another device, changed your password, or Telegram invalidated old sessions). Re-run `python scripts/login.py` and replace the value in `.env`.

**Nothing in the log file.** Check `TG_LOG_PATH` — the default parent directory (`~/.local/state/tg-mcp/`) is created on first run, but a read-only home or a typo in the env var will prevent writes. The server cannot warn you about this on stdout because stdout is the MCP transport.

## Security

- The server is **read-only on channels** and **send-to-self only** for posting. There is no Telegram API surface for delete, edit-of-others, ban, invite, or leave.
- **The whitelist of channels lives in the prompt, not in the server.** Every call passes the channels it wants to act on. The server has no `ALLOWED_CHANNELS` env var, no on-disk allow-list, no in-memory cache. This means policy ("which channels do my scheduled digests cover?") belongs to the caller (a Cowork scheduled task, an ad-hoc question, an MCP client UI).
- **No on-disk session.** The session string lives in `.env` and in your MCP host's config block — nowhere else. `.gitignore` excludes both `.env` and `*.session*`.
- **No stdout writes.** The server is enforced by a regression test (`tests/test_server_stdio.py`) that launches the actual process and asserts empty stdout. A stray `print()` would break Cowork integration silently — the test prevents that.
- The session string is the credential boundary. If you suspect it has leaked, revoke active sessions via Telegram's "Active Sessions" UI and re-run `scripts/login.py`.

## Development

```bash
uv sync
uv run pytest -q          # unit tests, ~80 cases, no network
uv run python -m tg_mcp.server </dev/null  # boots, exits on EOF, must produce 0 bytes on stdout
```

Conventional commits in English (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`).

Plans live under `docs/plans/<branch-slug>.md`. Architectural decisions (ADRs) and module overviews (CODEMAPS) are added under `docs/ADR/` and `docs/CODEMAPS/` by the documentation agent when structural decisions land.
