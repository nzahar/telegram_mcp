# Setup memo — what the operator does

Things only you can do before this MCP server is usable. Each step lists exactly what the system needs from you and where to put it.

> This memo covers credentials, accounts, and host-side configuration. Code installation (`uv sync`, running tests) is automated — see the README. Architecture lives in `docs/CODEMAPS/tg_mcp.md` and `docs/ADR/`.

## Prerequisites

- [ ] **A Telegram account.** Use the account whose messages and channels you want the server to read on your behalf. The session string the server holds gives the server full read/write access to this account — pick the one you're comfortable with that level of trust on.
- [ ] **A phone you can receive SMS / Telegram codes on.** Telegram sends a login code during step 2. If you have 2FA enabled on this account, also have your password ready.
- [ ] **An MCP host** to call the server. Cowork or any other MCP-capable client (Claude Desktop, an IDE plugin, your own integration).

## Step 1 — Create a Telegram API application

Telegram requires every MTProto client to register an "application" so it can be identified. You'll do this once per account.

- [ ] Go to <https://my.telegram.org/apps> and log in with your phone number. (You'll get a code via Telegram itself, not SMS — open the official Telegram app to copy it.)
- [ ] Fill the "Create new application" form:
  - **App title:** anything (e.g. `tg-mcp`)
  - **Short name:** anything alphanumeric (e.g. `tg_mcp`)
  - **Platform:** Desktop
  - **Description:** optional
- [ ] After submission, copy **`api_id`** (a small integer) and **`api_hash`** (a 32-char hex string). These two values are not secrets in the password sense — they identify the application, not your account — but treat them as semi-private (do not commit them to public repos).

You'll paste both into `.env` in step 3.

## Step 2 — Generate a Telegram session string

The server authenticates as your account via a Telethon `StringSession`. You generate it once interactively; the server then reuses it without ever prompting again.

- [ ] From the repo root:

  ```bash
  uv run python scripts/login.py --out /tmp/tg-session.txt
  ```

  The script prompts on stderr; the session string is written to `/tmp/tg-session.txt` at mode `0600`. (Default mode without `--out` prints to stdout — avoid that under `set -x` or in CI, where the secret would land in logs.)

- [ ] Answer the prompts:
  - **Phone:** in international format, e.g. `+12025550100`.
  - **Code:** the digits Telegram sends to that number (check the official Telegram app or SMS).
  - **2FA password:** only if you have two-factor auth on the account.

- [ ] Open `/tmp/tg-session.txt` and copy the single long line. You'll paste it into `.env` next. **Delete the temp file afterwards** — `rm /tmp/tg-session.txt`.

The session string is the credential that gives the server (and anyone who steals the string) full account access. Treat it like a password.

## Step 3 — Fill in `.env`

- [ ] In the repo root:

  ```bash
  cp .env.example .env
  ```

- [ ] Open `.env` and paste in:
  - `TG_API_ID=` — the integer from step 1
  - `TG_API_HASH=` — the hex string from step 1
  - `TG_SESSION_STRING=` — the long string from step 2
  - `TG_LOG_PATH=` — leave blank to use the default `~/.local/state/tg-mcp/server.log`, or set an absolute path
  - `TG_LOG_LEVEL=INFO` — `DEBUG` if you want verbose Telethon output

- [ ] `.env` is in `.gitignore`, but verify with `git status` that it does not appear as untracked. Never commit it.

## Step 4 — Register the server in your MCP host

This is where the host learns how to spawn the server and what env to give it.

### For Cowork (or any host using the `mcpServers` block)

- [ ] Locate the host's MCP config (Cowork: connector settings; Claude Desktop: `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows).
- [ ] Add an entry under `mcpServers`. Replace `/absolute/path/to/telegram_mcp` with the path on the machine that will run the server:

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

- [ ] Decide: put credentials in the host's `env` block (above), **or** rely on the server reading `.env` from the repo directory at startup. Both work. The host-side `env` block is preferred for Cowork because it survives a fresh `git clone` and isolates credentials per host. The `.env` file is preferred for local debugging.
- [ ] Restart the MCP host so it re-spawns the server with the new config.

### For a different host

Same shape — `command`, `args`, `env`. Refer to the host's documentation; the contract is just "spawn `python -m tg_mcp.server` and speak stdio JSON-RPC to it".

## Step 5 — Verify

- [ ] From the repo root, **smoke-test the server locally**:

  ```bash
  uv run python -m tg_mcp.server </dev/null
  ```

  Expected: exits with code 0, prints **nothing** to stdout, **nothing** to stderr. If you see any output, something is misconfigured — check `cat ~/.local/state/tg-mcp/server.log` (or your `TG_LOG_PATH`).

- [ ] **Smoke-test from the host.** Open a session, ask the host to list MCP tools — `tg-mcp` should be present with three tools: `search_channels`, `get_recent`, `send_to_self`. If it's missing, check the host's MCP logs.

- [ ] **First real call.** Ask the host to run something like:

  > "Use tg-mcp.get_recent to pull the last 3 messages from @durov."

  Watch `tail -f ~/.local/state/tg-mcp/server.log` in another terminal. You should see `tool_call name=get_recent ...` followed by `tool_done name=get_recent elapsed_ms=...`. The host displays the messages.

If `get_recent` returns an `ErrorEntry` with `error=channel_not_found`, your account doesn't have access to that channel — try a public one like `@durov`. See `README.md` § Troubleshooting for the full error vocabulary.

## Operational notes (later)

- **Rotating the session string.** If you ever suspect the session leaked (e.g. it ended up in CI logs), revoke it from inside Telegram: Settings → Devices → terminate the suspicious session. Then re-run step 2 and replace `TG_SESSION_STRING` in `.env` and/or the host's `env` block.
- **Where the log lives.** `~/.local/state/tg-mcp/server.log` by default, rotates at 1 MB × 5 backups. Override with `TG_LOG_PATH`.
- **Channel access.** The server can only reach what your account can reach. Public channels: by `@username`. Private channels: only those your account has joined; pass the numeric chat ID (your host or a Telegram client can show it).
- **No persistent allow-list.** This server intentionally keeps no list of "channels I'm allowed to use" — see ADR-0001. Policy ("which channels does my morning digest cover?") lives in your prompt, not in the server. If you change your mind tomorrow, change the prompt; no server config edit needed.

## What you do NOT need to do

The repo handles these automatically — listed here so you don't go looking:

- `uv sync` to install dependencies → in the README's Install section.
- Running tests → `uv run pytest -q` from the repo root.
- Creating directories for logs → the server creates them on first run.
- Anything inside `src/`, `scripts/`, `tests/` — the implementation is done and tested.
