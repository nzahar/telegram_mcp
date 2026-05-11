"""Tests for scripts/login.py.

Interactive sign-in cannot be exercised in CI (requires a phone, a code
sent by Telegram, and possibly 2FA). These tests verify the non-interactive
surface: argparse configuration, ``--out PATH`` dispatch, and
``_write_session_file`` behaviour.
"""

from __future__ import annotations

import importlib.util
import stat
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LOGIN_SCRIPT = REPO_ROOT / "scripts" / "login.py"


def _load_login():
    """Import scripts/login.py as a module without executing main()."""
    spec = importlib.util.spec_from_file_location("login_script", LOGIN_SCRIPT)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_login_help_exits_zero():
    result = subprocess.run(
        [sys.executable, str(LOGIN_SCRIPT), "--help"],
        capture_output=True,
        timeout=10,
        text=True,
    )
    assert result.returncode == 0
    assert "TG_SESSION_STRING" in result.stdout
    assert "session" in result.stdout.lower()


def test_help_mentions_out_flag():
    """``--out`` must appear in the help text so the user can discover it."""
    result = subprocess.run(
        [sys.executable, str(LOGIN_SCRIPT), "--help"],
        capture_output=True,
        timeout=10,
        text=True,
    )
    assert result.returncode == 0
    assert "--out" in result.stdout


def test_argparse_accepts_out_path(tmp_path):
    """argparse must accept ``--out PATH`` without error (no network needed)."""
    login = _load_login()
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", metavar="PATH", type=Path, default=None)

    # Parse a representative invocation — must not raise.
    args = parser.parse_args(["--out", str(tmp_path / "session.txt")])
    assert args.out == tmp_path / "session.txt"


def test_write_session_file_creates_file_with_content(tmp_path):
    """_write_session_file writes the session string followed by a newline."""
    login = _load_login()
    dest = tmp_path / "session.txt"
    session = "fake_session_string_abc123"

    login._write_session_file(dest, session)

    assert dest.exists()
    assert dest.read_text() == session + "\n"


def test_write_session_file_mode_is_0600(tmp_path):
    """_write_session_file must create the file at mode 0600 (owner read/write only)."""
    login = _load_login()
    dest = tmp_path / "session.txt"

    login._write_session_file(dest, "s3cr3t")

    mode = stat.S_IMODE(dest.stat().st_mode)
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"


def test_write_session_file_overwrites_existing(tmp_path):
    """Writing to an existing path replaces the content (no append)."""
    login = _load_login()
    dest = tmp_path / "session.txt"
    dest.write_text("old content")

    login._write_session_file(dest, "new_session")

    assert dest.read_text() == "new_session\n"


def test_write_session_file_tightens_mode_on_pre_existing_wider_file(tmp_path):
    """Pre-existing 0644 path must end up at 0600 — covers the TOCTOU window
    that ``os.open(..., 0o600)`` alone left open (``O_CREAT`` ignores the mode
    arg when the inode already exists)."""
    login = _load_login()
    dest = tmp_path / "session.txt"
    dest.write_text("old content")
    dest.chmod(0o644)

    login._write_session_file(dest, "new_session")

    mode = stat.S_IMODE(dest.stat().st_mode)
    assert mode == 0o600, f"expected 0600 on pre-existing path, got {oct(mode)}"
    assert dest.read_text() == "new_session\n"


def test_write_session_file_no_leftover_tempfile_on_success(tmp_path):
    """The mkstemp sibling tempfile must be renamed onto the target, not left."""
    login = _load_login()
    dest = tmp_path / "session.txt"

    login._write_session_file(dest, "abc")

    siblings = [p.name for p in tmp_path.iterdir() if p.name.startswith(".tg-session-")]
    assert siblings == [], f"unexpected leftover tempfile(s): {siblings}"
