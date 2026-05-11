"""Integration tests that require a live Telegram session.

Skipped from the default pytest run because they need:
  - a valid TG_SESSION_STRING, TG_API_ID, TG_API_HASH in the environment,
  - network access to Telegram's MTProto endpoints,
  - real channels that the signed-in account can read.

Run locally with::

    uv run pytest -m integration

Use a small set of channels (e.g. @durov) and short ``since`` values to
keep API usage minimal.
"""

from __future__ import annotations

import os

import pytest

from tg_mcp.client import shutdown
from tg_mcp.tools import get_recent


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_credentials():
    missing = [
        k for k in ("TG_API_ID", "TG_API_HASH", "TG_SESSION_STRING") if not os.environ.get(k)
    ]
    if missing:
        pytest.skip(f"integration env not set: {missing}")


async def test_get_recent_from_durov_returns_messages():
    """Smoke test: @durov has been posting forever; if this fails the
    credentials or network are at fault, not the code under test."""
    try:
        result = await get_recent("@durov", limit=3)
    finally:
        await shutdown()
    assert not result.partial
    assert len(result.items) >= 1
