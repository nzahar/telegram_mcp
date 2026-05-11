"""Generate a Telethon StringSession by signing in interactively.

Usage:
    python scripts/login.py                  # session string to stdout
    python scripts/login.py --out PATH       # session string to a file (mode 0600)

Reads ``TG_API_ID`` and ``TG_API_HASH`` from the environment, prompting if
absent. Everything except the session string (prompts, status messages) goes
to stderr.

Security note: the session string grants full read/write access to the
signed-in Telegram account. Treat it like a password. The script keeps the
session in memory via ``StringSession()`` — it never writes a ``*.session``
file to disk. When using the default stdout output, beware of shells with
``set -x`` enabled and CI environments that capture stdout — both will log
the secret. ``--out`` writes directly to a file with ``0600`` permissions
and avoids both pitfalls.

The script is intentionally standalone — no import of ``tg_mcp`` — so a
user with the spec in hand can run it from a fresh checkout before
configuring the rest of the server.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

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


def _write_session_file(path: Path, session_string: str) -> None:
    # Create with 0600 atomically — write through an exclusive-create handle
    # before the secret reaches the filesystem at any wider permission.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, session_string.encode("utf-8"))
        os.write(fd, b"\n")
    finally:
        os.close(fd)
    # Defensive: re-stat and tighten if umask widened the mode (some
    # filesystems / sandboxes ignore the mode arg to open()).
    current = stat.S_IMODE(path.stat().st_mode)
    if current & 0o077:
        path.chmod(0o600)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tg-mcp-login",
        description=(
            "Sign in to Telegram interactively and emit a Telethon StringSession "
            "for use as TG_SESSION_STRING. Default: prints the session string to "
            "stdout. With --out PATH the string is written to that file at mode "
            "0600 instead. The session is held in memory only -- no *.session "
            "file is written."
        ),
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        type=Path,
        default=None,
        help=(
            "Write the session string to PATH (created at mode 0600) instead "
            "of stdout. Recommended in shells with `set -x` or in CI."
        ),
    )
    args = parser.parse_args()

    api_id = _resolve_api_id()
    api_hash = _resolve_api_hash()

    print(
        "Signing in. You will be prompted for your phone, the code Telegram "
        "sends, and (if 2FA is enabled) your account password.",
        file=sys.stderr,
    )

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        session_string = client.session.save()

    if args.out is None:
        print("Done. Session string follows on stdout:", file=sys.stderr)
        print(session_string)
    else:
        _write_session_file(args.out, session_string)
        print(f"Done. Session string written to {args.out} (mode 0600).", file=sys.stderr)


if __name__ == "__main__":
    main()
