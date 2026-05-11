"""Tests for tg_mcp.tools.search_channels."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tg_mcp.client import ChannelResolutionError
from tg_mcp.models import ErrorEntry, Message
from tg_mcp.tools import search_channels

from tests.conftest import FakeClient, FakeEntity, FakeRawMessage


def _ago(seconds: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


class TestHappyPath:
    async def test_returns_messages_for_one_channel(self, fake_client):
        entity = FakeEntity(username="durov")
        msgs = [
            FakeRawMessage(id=10, text="latest", date=_ago(60), views=100),
            FakeRawMessage(id=9, text="older", date=_ago(120), views=50),
        ]
        client = fake_client(FakeClient(channels={"@durov": (entity, msgs)}))

        result = await search_channels(channels=["@durov"], query="", since="1h")

        assert result.partial is False
        assert len(result.items) == 2
        first = result.items[0]
        assert isinstance(first, Message)
        assert first.id == 10
        assert first.text == "latest"
        assert first.link == "https://t.me/durov/10"
        assert first.views == 100
        assert first.channel == "@durov"

    async def test_multi_channel_messages_in_order(self, fake_client):
        e1 = FakeEntity(username="a")
        e2 = FakeEntity(username="b")
        client = fake_client(
            FakeClient(
                channels={
                    "@a": (e1, [FakeRawMessage(1, "from-a", _ago(10))]),
                    "@b": (e2, [FakeRawMessage(2, "from-b", _ago(10))]),
                }
            )
        )

        result = await search_channels(channels=["@a", "@b"], query="", since="1h")

        assert [m.text for m in result.items] == ["from-a", "from-b"]

    async def test_since_cutoff_breaks_iteration(self, fake_client):
        entity = FakeEntity(username="ch")
        msgs = [
            FakeRawMessage(3, "new", _ago(30)),
            FakeRawMessage(2, "borderline", _ago(60)),
            FakeRawMessage(1, "too-old", _ago(3600)),
        ]
        client = fake_client(FakeClient(channels={"@ch": (entity, msgs)}))

        # since=2m → only messages newer than 2 minutes ago survive.
        result = await search_channels(channels=["@ch"], query="", since="2m")

        ids = [m.id for m in result.items if isinstance(m, Message)]
        assert 3 in ids
        assert 1 not in ids

    async def test_numeric_chat_id_link_is_none(self, fake_client):
        entity = FakeEntity(username=None)
        client = fake_client(
            FakeClient(channels={123: (entity, [FakeRawMessage(1, "x", _ago(5))])})
        )

        result = await search_channels(channels=[123], query="", since="1h")

        msg = result.items[0]
        assert isinstance(msg, Message)
        assert msg.link is None


class TestErrorHandling:
    async def test_broken_channel_returns_error_entry(self, fake_client):
        e_good = FakeEntity(username="good")
        client = fake_client(
            FakeClient(
                channels={"@good": (e_good, [FakeRawMessage(1, "ok", _ago(5))])},
                entity_errors={"@bad": ValueError("no such entity")},
            )
        )

        result = await search_channels(
            channels=["@bad", "@good"], query="", since="1h"
        )

        assert len(result.items) == 2
        bad = result.items[0]
        good = result.items[1]
        assert isinstance(bad, ErrorEntry)
        assert bad.channel == "@bad"
        assert bad.error == "channel_not_found"
        assert isinstance(good, Message)
        assert result.partial is False

    async def test_other_channels_continue_after_bad_one(self, fake_client):
        e_a = FakeEntity(username="a")
        e_c = FakeEntity(username="c")
        client = fake_client(
            FakeClient(
                channels={
                    "@a": (e_a, [FakeRawMessage(1, "a-msg", _ago(5))]),
                    "@c": (e_c, [FakeRawMessage(2, "c-msg", _ago(5))]),
                },
                entity_errors={"@b": ValueError("nope")},
            )
        )

        result = await search_channels(
            channels=["@a", "@b", "@c"], query="", since="1h"
        )

        types = [type(x).__name__ for x in result.items]
        assert types == ["Message", "ErrorEntry", "Message"]


class TestFloodRetry:
    async def test_flood_wait_retried_once(self, fake_client, fast_flood_retry, flood):
        entity = FakeEntity(username="ch")
        # First iter call raises; the same factory will be re-invoked by
        # with_flood_retry, on which we want a clean list to come back.
        attempts = {"n": 0}

        def behaviour():
            attempts["n"] += 1
            if attempts["n"] == 1:
                return [flood(3)]
            return [FakeRawMessage(1, "after-retry", _ago(5))]

        client = fake_client(FakeClient(channels={"@ch": (entity, behaviour)}))

        result = await search_channels(channels=["@ch"], query="", since="1h")

        assert attempts["n"] == 2
        assert len(result.items) == 1
        msg = result.items[0]
        assert isinstance(msg, Message)
        assert msg.text == "after-retry"
        assert result.partial is False

    async def test_double_flood_marks_partial(
        self, fake_client, fast_flood_retry, flood
    ):
        entity = FakeEntity(username="ch")

        def behaviour():
            return [flood(5)]

        client = fake_client(FakeClient(channels={"@ch": (entity, behaviour)}))

        result = await search_channels(channels=["@ch"], query="", since="1h")

        assert result.partial is True
        assert len(result.items) == 1
        err = result.items[0]
        assert isinstance(err, ErrorEntry)
        assert err.error == "flood_wait_exceeded"


class TestClientInitialisation:
    async def test_client_initialised_once_across_channels(self, monkeypatch):
        """get_client must not be re-resolved per channel — it's a singleton."""
        from tg_mcp import tools

        e1 = FakeEntity(username="a")
        e2 = FakeEntity(username="b")
        shared = FakeClient(
            channels={
                "@a": (e1, [FakeRawMessage(1, "x", _ago(5))]),
                "@b": (e2, [FakeRawMessage(2, "y", _ago(5))]),
            }
        )
        call_count = {"n": 0}

        async def fake_get_client():
            call_count["n"] += 1
            return shared

        monkeypatch.setattr(tools, "get_client", fake_get_client)

        await tools.search_channels(channels=["@a", "@b"], query="", since="1h")

        assert call_count["n"] == 1
