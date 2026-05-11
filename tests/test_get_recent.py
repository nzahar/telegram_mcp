"""Tests for tg_mcp.tools.get_recent."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tg_mcp.models import ErrorEntry, Message
from tg_mcp.tools import _build_message_link, get_recent

from tests.conftest import FakeClient, FakeEntity, FakeRawMessage


def _ago(seconds: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


class TestBuildMessageLink:
    """Unit tests for _build_message_link — isolated from FakeClient."""

    def test_lowercase_already_lower(self):
        entity = FakeEntity(username="durov")
        assert _build_message_link(entity, 42) == "https://t.me/durov/42"

    def test_mixed_case_username_is_lowercased(self):
        """Telethon may return the username in its original mixed case; the link
        must be lowercase for symmetry with _send_link and Telegram URL conventions."""
        entity = FakeEntity(username="DuRoV")
        assert _build_message_link(entity, 7) == "https://t.me/durov/7"

    def test_none_username_returns_none(self):
        assert _build_message_link(FakeEntity(username=None), 1) is None

    def test_empty_username_returns_none(self):
        assert _build_message_link(FakeEntity(username=""), 1) is None

    def test_no_username_attr_returns_none(self):
        class _EntityWithout:
            pass

        assert _build_message_link(_EntityWithout(), 1) is None


class TestGetRecent:
    async def test_returns_messages(self, fake_client):
        entity = FakeEntity(username="ch")
        msgs = [
            FakeRawMessage(2, "newer", _ago(5), views=10),
            FakeRawMessage(1, "older", _ago(60), views=5),
        ]
        client = fake_client(FakeClient(channels={"@ch": (entity, msgs)}))

        result = await get_recent("@ch", limit=10)

        assert result.partial is False
        assert [m.id for m in result.items if isinstance(m, Message)] == [2, 1]
        assert result.items[0].link == "https://t.me/ch/2"

    async def test_passes_limit_to_iter_messages(self, fake_client):
        entity = FakeEntity(username="ch")
        client = fake_client(FakeClient(channels={"@ch": (entity, [])}))

        await get_recent("@ch", limit=7)

        assert client.iter_calls
        _entity, limit, search = client.iter_calls[0]
        assert limit == 7
        assert search is None

    async def test_broken_channel_returns_single_error_entry(self, fake_client):
        client = fake_client(
            FakeClient(entity_errors={"@bad": ValueError("missing")})
        )

        result = await get_recent("@bad")

        assert len(result.items) == 1
        err = result.items[0]
        assert isinstance(err, ErrorEntry)
        assert err.error == "channel_not_found"
        assert result.partial is False

    async def test_double_flood_returns_partial_true(
        self, fake_client, fast_flood_retry, flood
    ):
        entity = FakeEntity(username="ch")

        def behaviour():
            return [flood(2)]

        client = fake_client(FakeClient(channels={"@ch": (entity, behaviour)}))

        result = await get_recent("@ch")

        assert result.partial is True
        assert isinstance(result.items[0], ErrorEntry)
        assert result.items[0].error == "flood_wait_exceeded"

    async def test_numeric_channel_link_is_none(self, fake_client):
        entity = FakeEntity(username=None)
        client = fake_client(
            FakeClient(channels={42: (entity, [FakeRawMessage(1, "x", _ago(5))])})
        )

        result = await get_recent(42)

        msg = result.items[0]
        assert isinstance(msg, Message)
        assert msg.link is None
        assert msg.channel == 42
