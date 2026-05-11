"""Telethon client lifecycle, channel resolution, since parsing, flood retry.

The client is a module-level lazy singleton created from environment
variables (``TG_API_ID``, ``TG_API_HASH``, ``TG_SESSION_STRING``). It is
connected on first tool call and disconnected by :func:`shutdown` at
server stop. The server never queries channels not passed explicitly in
the current call — this module only resolves what the caller hands in.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.sessions import StringSession

from .models import ChannelRef


__all__ = [
    "ChannelRef",
    "ChannelResolutionError",
    "FloodLimitExceeded",
    "get_client",
    "shutdown",
    "parse_since",
    "resolve_channel",
    "with_flood_retry",
]


class ChannelResolutionError(Exception):
    """Raised when a channel reference cannot be resolved.

    Carries a machine-readable ``code`` (mapped to ``ErrorEntry.error``) and a
    human ``detail``. Tools catch this and convert it into an ``ErrorEntry``
    entry alongside successful messages, so a single bad channel does not
    break the whole batch.
    """

    def __init__(self, channel: ChannelRef, code: str, detail: Optional[str] = None):
        super().__init__(f"{code}: {channel} ({detail or ''})")
        self.channel = channel
        self.code = code
        self.detail = detail


class FloodLimitExceeded(Exception):
    """Raised by :func:`with_flood_retry` after a second consecutive FloodWaitError."""

    def __init__(self, seconds: int):
        super().__init__(f"flood wait exceeded; second wait would be {seconds}s")
        self.seconds = seconds


_log = logging.getLogger("tg_mcp.client")

_client: Optional[TelegramClient] = None
_client_lock = asyncio.Lock()


async def get_client() -> TelegramClient:
    """Return the lazily-initialised, connected Telethon client.

    Reads credentials from env on first call. Subsequent calls return the same
    instance. If the previous singleton is present but disconnected (Telethon
    dropped the link mid-session), it is explicitly disconnected before a new
    client replaces it so background sender/keepalive tasks do not leak.

    Raises ``RuntimeError`` if credentials are missing or the session is not
    authorised.
    """
    global _client
    if _client is not None and _client.is_connected():
        return _client

    async with _client_lock:
        if _client is not None and _client.is_connected():
            return _client

        prev = _client
        _client = None
        if prev is not None:
            try:
                await prev.disconnect()
            except (ConnectionError, OSError) as e:
                # Stale-client cleanup hit a network/socket error; log but
                # don't propagate — we're about to replace the client anyway.
                # A narrow catch keeps programmer errors (AttributeError,
                # TypeError, …) visible.
                _log.warning("stale client disconnect failed: %r", e)

        try:
            api_id = int(os.environ["TG_API_ID"])
            api_hash = os.environ["TG_API_HASH"]
            session = os.environ["TG_SESSION_STRING"]
        except KeyError as e:
            raise RuntimeError(
                f"missing required env var {e.args[0]}; "
                "set TG_API_ID, TG_API_HASH, TG_SESSION_STRING"
            ) from e
        except ValueError as e:
            raise RuntimeError("TG_API_ID must be an integer") from e

        client = TelegramClient(StringSession(session), api_id, api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise RuntimeError(
                "TG_SESSION_STRING is present but not authorised; "
                "regenerate with `python scripts/login.py`"
            )
        _client = client
        return _client


async def shutdown() -> None:
    """Disconnect the singleton if connected. Safe to call multiple times."""
    global _client
    if _client is None:
        return
    try:
        if _client.is_connected():
            await _client.disconnect()
    finally:
        _client = None


_RELATIVE_RE = re.compile(r"^\s*(\d+)\s*([dhm])\s*$", re.IGNORECASE)


def parse_since(value: str) -> datetime:
    """Parse a ``since`` argument into a timezone-aware UTC datetime.

    Accepts:
      - relative: ``"7d"``, ``"24h"``, ``"30m"`` (now-UTC minus the delta)
      - ISO-8601 date: ``"2026-05-01"`` (midnight UTC)
      - ISO-8601 datetime: naive treated as UTC; aware preserved as-is
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("`since` must be a non-empty string")

    m = _RELATIVE_RE.match(value)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        delta = {
            "d": timedelta(days=n),
            "h": timedelta(hours=n),
            "m": timedelta(minutes=n),
        }[unit]
        return datetime.now(timezone.utc) - delta

    try:
        dt = datetime.fromisoformat(value)
    except ValueError as e:
        raise ValueError(
            f"invalid `since`: {value!r}; expected Nd/Nh/Nm or ISO-8601"
        ) from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def resolve_channel(client: TelegramClient, ref: ChannelRef) -> Any:
    """Resolve a channel reference (``@username`` or int chat_id) to a Telethon entity.

    Translates the common Telethon errors into :class:`ChannelResolutionError`
    so the calling tool can produce a structured ``ErrorEntry``.
    """
    try:
        return await client.get_entity(ref)
    except UsernameNotOccupiedError as e:
        raise ChannelResolutionError(ref, "channel_not_found", str(e)) from e
    except UsernameInvalidError as e:
        raise ChannelResolutionError(ref, "username_invalid", str(e)) from e
    except ChannelPrivateError as e:
        raise ChannelResolutionError(ref, "channel_private", str(e)) from e
    except ValueError as e:
        raise ChannelResolutionError(ref, "channel_not_found", str(e)) from e


async def with_flood_retry(
    factory: Callable[[], Awaitable[Any]],
    log: logging.Logger,
) -> Any:
    """Run ``factory()``; on ``FloodWaitError`` wait the reported seconds and retry once.

    A second consecutive ``FloodWaitError`` is converted to
    :class:`FloodLimitExceeded`, which tools translate into a ``partial=True``
    response. ``factory`` must be re-callable — receive a fresh coroutine each
    invocation (do not pass an already-awaited coroutine).
    """
    try:
        return await factory()
    except FloodWaitError as first:
        wait = max(first.seconds, 0)
        log.warning("flood_wait_first attempt=1 wait=%ss", wait)
        await asyncio.sleep(wait)
        try:
            return await factory()
        except FloodWaitError as second:
            log.warning(
                "flood_wait_second attempt=2 wait=%ss -> surfacing as partial",
                second.seconds,
            )
            raise FloodLimitExceeded(second.seconds) from second
