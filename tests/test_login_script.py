"""Smoke test for scripts/login.py.

Interactive sign-in cannot be exercised in CI (requires a phone, a code
sent by Telegram, and possibly 2FA). This test only verifies the script
loads and ``--help`` exits cleanly — enough to catch import errors,
missing dependencies, or argparse misconfiguration.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_login_help_exits_zero():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "login.py"), "--help"],
        capture_output=True,
        timeout=10,
        text=True,
    )
    assert result.returncode == 0
    assert "TG_SESSION_STRING" in result.stdout
    assert "session" in result.stdout.lower()
