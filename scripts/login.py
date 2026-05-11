"""Generate a Telethon StringSession by signing in interactively.

Usage:
    python scripts/login.py

Reads ``TG_API_ID`` and ``TG_API_HASH`` from the environment, prompting if
absent. The resulting session string is printed to **stdout**; everything
else (prompts, status, warnings) goes to **stderr** so the caller can
``python scripts/login.py > .env.session`` if they want.

Security note: the session string grants full read/write access to the
signed-in Telegram account. Treat it like a password. The script keeps the
session in memory via ``StringSession()`` — it never writes a ``*.session``
file to disk.

The script is intentionally standalone — no import of ``tg_mcp`` — so a
user with the spec in hand can run it from a fresh checkout before
configuring the rest of the server.
"""

from __future__ import annotations

import argparse
import os
import sys

from telethon import TelegramClient
from telethon.sessions import StringSession


def _prompt(label: str) -> str:
    return input(f"{label}: ").strip()


def _resolve_api_id() -> int:
    raw = os.environ.get("TG_API_ID") or _prompt("TG_API_ID")
    try:
        return int(raw)
    except ValueError:
        print(f"error: TG_API_ID must be an integer, got {raw!r}", file=sys.stderr)
        sys.exit(2)


def _resolve_api_hash() -> str:
    return os.environ.get("TG_API_HASH") or _prompt("TG_API_HASH")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tg-mcp-login",
        description=(
            "Sign in to Telegram interactively and print a Telethon StringSession "
            "to stdout. Save the output as TG_SESSION_STRING in your .env. "
            "The session is held in memory only -- no *.session file is written."
        ),
    )
    parser.parse_args()

    api_id = _resolve_api_id()
    api_hash = _resolve_api_hash()

    print(
        "Signing in. You will be prompted for your phone, the code Telegram "
        "sends, and (if 2FA is enabled) your account password.",
        file=sys.stderr,
    )

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        session_string = client.session.save()

    print("Done. Session string follows on stdout:", file=sys.stderr)
    print(session_string)


if __name__ == "__main__":
    main()
