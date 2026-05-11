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

import tg_mcp.client as _client_module
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


class TestGetClientStaleReconnect:
    """get_client must disconnect a stale (not connected) singleton before rebuilding."""

    async def test_stale_client_disconnect_is_awaited(self, monkeypatch):
        """When the module-level _client is present but not connected, get_client
        must call disconnect() on it before constructing a replacement.  This
        prevents background keepalive tasks on the dead client from leaking.
        """
        disconnect_calls: list[str] = []

        class _StaleClient:
            def is_connected(self) -> bool:
                return False

            async def disconnect(self) -> None:
                disconnect_calls.append("disconnect")

        class _FreshClient:
            """Stands in for the new TelegramClient that replaces the stale one."""

            def __init__(self, *_a, **_kw):
                pass

            async def connect(self) -> None:
                pass

            def is_connected(self) -> bool:
                return True

            async def is_user_authorized(self) -> bool:
                return True

        # Inject a stale singleton directly into the module.
        monkeypatch.setattr(_client_module, "_client", _StaleClient())
        monkeypatch.setattr(_client_module, "_client_lock", __import__("asyncio").Lock())

        # Patch TelegramClient so no real network call happens.
        monkeypatch.setattr(_client_module, "TelegramClient", _FreshClient)

        # Provide required env vars.
        monkeypatch.setenv("TG_API_ID", "1")
        monkeypatch.setenv("TG_API_HASH", "abc")
        monkeypatch.setenv("TG_SESSION_STRING", "test_session")

        # Import and stub StringSession so the ctor doesn't validate the string.
        from telethon.sessions import StringSession as _SS
        monkeypatch.setattr(_client_module, "StringSession", lambda s: s)

        from tg_mcp.client import get_client
        client = await get_client()

        assert disconnect_calls == ["disconnect"], (
            "expected stale client's disconnect() to be awaited exactly once; "
            f"got {disconnect_calls!r}"
        )
        assert isinstance(client, _FreshClient)

        # Clean up the module singleton so it doesn't affect other tests.
        monkeypatch.setattr(_client_module, "_client", None)

    async def test_stale_client_network_disconnect_error_is_swallowed(self, monkeypatch):
        """A ConnectionError / OSError from the old singleton's disconnect()
        must not propagate — the failure is logged and reconnection continues.
        The narrow catch is documented in ADR-0001/CODEMAP gotchas; broader
        errors (programmer mistakes) are deliberately NOT caught — see the
        sister test below.
        """
        class _DyingClient:
            def is_connected(self) -> bool:
                return False

            async def disconnect(self) -> None:
                raise ConnectionError("transport closed")

        class _FreshClient:
            def __init__(self, *_a, **_kw):
                pass

            async def connect(self) -> None:
                pass

            def is_connected(self) -> bool:
                return True

            async def is_user_authorized(self) -> bool:
                return True

        monkeypatch.setattr(_client_module, "_client", _DyingClient())
        monkeypatch.setattr(_client_module, "_client_lock", __import__("asyncio").Lock())
        monkeypatch.setattr(_client_module, "TelegramClient", _FreshClient)
        monkeypatch.setenv("TG_API_ID", "1")
        monkeypatch.setenv("TG_API_HASH", "abc")
        monkeypatch.setenv("TG_SESSION_STRING", "test_session")
        monkeypatch.setattr(_client_module, "StringSession", lambda s: s)

        from tg_mcp.client import get_client
        client = await get_client()
        assert isinstance(client, _FreshClient)

        monkeypatch.setattr(_client_module, "_client", None)

    async def test_stale_client_programmer_error_propagates(self, monkeypatch):
        """Unexpected exceptions (AttributeError, TypeError, …) from the stale
        client's disconnect path are NOT swallowed — they indicate a
        programmer error or API drift and must surface, not silently hide.
        """
        class _BrokenClient:
            def is_connected(self) -> bool:
                return False

            async def disconnect(self) -> None:
                raise AttributeError("prev client is the wrong object type")

        monkeypatch.setattr(_client_module, "_client", _BrokenClient())
        monkeypatch.setattr(_client_module, "_client_lock", __import__("asyncio").Lock())
        monkeypatch.setenv("TG_API_ID", "1")
        monkeypatch.setenv("TG_API_HASH", "abc")
        monkeypatch.setenv("TG_SESSION_STRING", "test_session")

        from tg_mcp.client import get_client
        with pytest.raises(AttributeError, match="wrong object type"):
            await get_client()

        monkeypatch.setattr(_client_module, "_client", None)


class TestFakeClientOffsetDateGuard:
    """FakeClient.iter_messages must raise NotImplementedError on offset_date.

    This is a regression guard: if a future code change passes offset_date to
    iter_messages (bypassing the in-loop date filter), the fake will surface
    the mismatch immediately rather than silently returning the wrong results.
    """

    def test_offset_date_raises_not_implemented(self):
        from tests.conftest import FakeClient, FakeEntity, FakeRawMessage
        from datetime import datetime, timezone

        entity = FakeEntity(username="ch")
        client = FakeClient(
            channels={"@ch": (entity, [FakeRawMessage(1, "x")])}
        )

        with pytest.raises(NotImplementedError, match="offset_date"):
            # iter_messages is sync (returns an async iterator); the guard fires
            # before any async iteration, so no await is needed here.
            client.iter_messages(entity, limit=10, offset_date=datetime.now(timezone.utc))
