"""Shared test fixtures and Telethon fakes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import pytest
from telethon.errors import FloodWaitError


class FakeEntity:
    def __init__(self, username: Optional[str] = None):
        self.username = username


class FakeRawMessage:
    """Mimics the subset of a Telethon ``Message`` we read in tools._to_message."""

    def __init__(
        self,
        id: int,
        text: str,
        date: Optional[datetime] = None,
        views: Optional[int] = None,
    ):
        self.id = id
        self.message = text
        self.text = text
        self.date = date or datetime.now(timezone.utc)
        self.views = views


class FakeSentMessage:
    def __init__(self, id: int):
        self.id = id


def _make_flood(seconds: int) -> FloodWaitError:
    return FloodWaitError(request=None, capture=seconds)


class _AsyncMessagesIter:
    def __init__(self, items: Iterable[Any]):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        item = self._items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeClient:
    """Configurable async fake for tg_mcp.tools tests.

    ``channels``: mapping ``ref -> (FakeEntity, iter_messages_behaviour)``.
      The behaviour is either:
        - list of FakeRawMessage (returned on every iter_messages call), or
        - callable() returning a list (re-invoked per call, useful for flood
          retry tests where attempt N raises and attempt N+1 succeeds).
    ``entity_errors``: mapping ``ref -> Exception`` to raise from get_entity.
    """

    def __init__(
        self,
        channels: Optional[dict] = None,
        entity_errors: Optional[dict] = None,
        send_behaviour: Any = None,
    ):
        self.channels = channels or {}
        self.entity_errors = entity_errors or {}
        self._send_behaviour = send_behaviour
        self.iter_calls: list[tuple] = []
        self.send_calls: list[tuple] = []
        self._send_counter = 0

    async def get_entity(self, ref):
        if ref in self.entity_errors:
            raise self.entity_errors[ref]
        if ref in self.channels:
            return self.channels[ref][0]
        raise ValueError(f"unknown entity: {ref!r}")

    def iter_messages(self, entity, limit=None, search=None, offset_date=None):
        if offset_date is not None:
            # Production tools currently filter by date in-loop, not via
            # offset_date. If that changes, the fake should be updated to
            # honour the kwarg rather than silently ignore it.
            raise NotImplementedError(
                "FakeClient.iter_messages does not implement offset_date; "
                "production tools filter via raw.date < since_dt instead."
            )
        self.iter_calls.append((entity, limit, search))
        for ref, (ent, behaviour) in self.channels.items():
            if ent is entity:
                items = behaviour() if callable(behaviour) else behaviour
                # Copy so a list-form behaviour isn't drained across calls
                # (callable behaviour already returns a fresh list each time).
                return _AsyncMessagesIter(list(items))
        return _AsyncMessagesIter([])

    async def send_message(self, chat, text, parse_mode=None):
        self.send_calls.append((chat, text, parse_mode))
        self._send_counter += 1
        b = self._send_behaviour
        if callable(b):
            return b(self._send_counter, chat, text)
        if isinstance(b, list):
            item = b[(self._send_counter - 1) % len(b)]
            if isinstance(item, BaseException):
                raise item
            return item
        return FakeSentMessage(id=1000 + self._send_counter)


@pytest.fixture
def fake_client(monkeypatch):
    """Patch tg_mcp.tools.get_client to return the test-provided FakeClient."""

    def _install(client: FakeClient) -> FakeClient:
        async def _get():
            return client

        monkeypatch.setattr("tg_mcp.tools.get_client", _get)
        return client

    return _install


@pytest.fixture
def fast_flood_retry(monkeypatch):
    """Replace asyncio.sleep in the client module so flood retries are instant."""

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr("tg_mcp.client.asyncio.sleep", _no_sleep)


@pytest.fixture
def flood(monkeypatch):
    """Helper returning a FloodWaitError-like exception with .seconds set."""

    def _make(seconds: int):
        return _make_flood(seconds)

    return _make
