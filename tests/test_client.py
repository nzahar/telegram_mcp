"""Tests for tg_mcp.client.with_flood_retry and resolve_channel error mapping.

Tool-layer integration tests (test_search.py, test_get_recent.py) cover
the retry path end-to-end in Slice 5; these are focused unit tests.
"""

from __future__ import annotations

import logging

import pytest
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)

from tg_mcp.client import (
    ChannelResolutionError,
    FloodLimitExceeded,
    resolve_channel,
    with_flood_retry,
)


def _flood(seconds: int) -> FloodWaitError:
    return FloodWaitError(request=None, capture=seconds)


@pytest.fixture
def log():
    return logging.getLogger("test")


class TestWithFloodRetry:
    async def test_first_call_succeeds_no_retry(self, log):
        calls = []

        async def factory():
            calls.append(1)
            return "ok"

        result = await with_flood_retry(factory, log)
        assert result == "ok"
        assert len(calls) == 1

    async def test_single_flood_then_retry_succeeds(self, monkeypatch, log):
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr("tg_mcp.client.asyncio.sleep", fake_sleep)

        calls = []

        async def factory():
            calls.append(1)
            if len(calls) == 1:
                raise _flood(7)
            return "second-ok"

        result = await with_flood_retry(factory, log)
        assert result == "second-ok"
        assert len(calls) == 2
        assert sleeps == [7]

    async def test_double_flood_raises_flood_limit_exceeded(self, monkeypatch, log):
        async def fake_sleep(seconds):
            return None

        monkeypatch.setattr("tg_mcp.client.asyncio.sleep", fake_sleep)

        async def factory():
            raise _flood(11)

        with pytest.raises(FloodLimitExceeded) as ei:
            await with_flood_retry(factory, log)
        assert ei.value.seconds == 11

    async def test_other_exceptions_propagate(self, log):
        async def factory():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await with_flood_retry(factory, log)

    async def test_non_flood_on_retry_propagates(self, monkeypatch, log):
        """First call raises FloodWait; retry raises a non-Flood error — must propagate."""
        async def fake_sleep(_):
            return None

        monkeypatch.setattr("tg_mcp.client.asyncio.sleep", fake_sleep)

        calls = []

        async def factory():
            calls.append(len(calls) + 1)
            if len(calls) == 1:
                raise _flood(2)
            raise ValueError("network error on retry")

        with pytest.raises(ValueError, match="network error on retry"):
            await with_flood_retry(factory, log)

        assert len(calls) == 2

    async def test_flood_wait_zero_seconds_sleeps_zero(self, monkeypatch, log):
        """FloodWaitError with seconds=0 must still invoke sleep(0)."""
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr("tg_mcp.client.asyncio.sleep", fake_sleep)

        calls = []

        async def factory():
            calls.append(1)
            if len(calls) == 1:
                raise _flood(0)
            return "ok-zero"

        result = await with_flood_retry(factory, log)
        assert result == "ok-zero"
        assert sleeps == [0]


class _FakeClient:
    def __init__(self, *, raises=None, returns=None):
        self._raises = raises
        self._returns = returns

    async def get_entity(self, ref):
        if self._raises is not None:
            raise self._raises
        return self._returns


class TestResolveChannel:
    async def test_returns_entity_on_success(self):
        entity = object()
        client = _FakeClient(returns=entity)
        assert await resolve_channel(client, "@durov") is entity

    async def test_username_not_occupied_maps_to_channel_not_found(self):
        client = _FakeClient(raises=UsernameNotOccupiedError(request=None))
        with pytest.raises(ChannelResolutionError) as ei:
            await resolve_channel(client, "@nope")
        assert ei.value.code == "channel_not_found"
        assert ei.value.channel == "@nope"

    async def test_username_invalid_maps_to_username_invalid(self):
        client = _FakeClient(raises=UsernameInvalidError(request=None))
        with pytest.raises(ChannelResolutionError) as ei:
            await resolve_channel(client, "@!!")
        assert ei.value.code == "username_invalid"

    async def test_channel_private_maps_to_channel_private(self):
        client = _FakeClient(raises=ChannelPrivateError(request=None))
        with pytest.raises(ChannelResolutionError) as ei:
            await resolve_channel(client, "@secret")
        assert ei.value.code == "channel_private"

    async def test_value_error_maps_to_channel_not_found(self):
        client = _FakeClient(raises=ValueError("cannot find any entity"))
        with pytest.raises(ChannelResolutionError) as ei:
            await resolve_channel(client, 123456)
        assert ei.value.code == "channel_not_found"
        assert ei.value.channel == 123456
