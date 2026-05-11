"""Tool implementations for the MCP server.

Each tool resolves the channel(s) passed in the call and acts only on those.
There is no whitelist anywhere — the server does not remember channels
between calls. The caller (a prompt or scheduled job) holds that policy.
"""

from __future__ import annotations

import logging
from typing import Optional

from .client import (
    ChannelRef,
    ChannelResolutionError,
    FloodLimitExceeded,
    get_client,
    parse_since,
    resolve_channel,
    with_flood_retry,
)
from .formatting import prepend_tag, split_for_telegram
from .models import ErrorEntry, Message, ReadResult, SendResult


log = logging.getLogger("tg_mcp.tools")


def _build_message_link(entity, msg_id: int) -> Optional[str]:
    username = getattr(entity, "username", None)
    return f"https://t.me/{username}/{msg_id}" if username else None


def _to_message(raw, channel_ref: ChannelRef, entity) -> Message:
    text = getattr(raw, "message", None)
    if text is None:
        text = getattr(raw, "text", "") or ""
    return Message(
        channel=channel_ref,
        id=raw.id,
        date=raw.date,
        text=text,
        link=_build_message_link(entity, raw.id),
        views=getattr(raw, "views", None),
    )


async def _collect_channel_messages(
    client,
    entity,
    channel_ref: ChannelRef,
    limit: int,
    search: Optional[str],
    since_dt,
):
    async def factory():
        out: list[Message] = []
        async for raw in client.iter_messages(
            entity, limit=limit, search=search or None
        ):
            if since_dt is not None and raw.date < since_dt:
                break
            out.append(_to_message(raw, channel_ref, entity))
        return out

    return await with_flood_retry(factory, log)


async def search_channels(
    channels: list[ChannelRef],
    query: str = "",
    since: Optional[str] = None,
    limit_per_channel: int = 50,
) -> ReadResult:
    """Search recent messages across multiple channels.

    Returns a ``ReadResult`` whose ``items`` mix ``Message`` and ``ErrorEntry``
    entries. ``partial=True`` if any channel was abandoned after a second
    consecutive FloodWaitError. Bad channels are reported as ``ErrorEntry``
    rather than aborting the batch.
    """
    client = await get_client()
    since_dt = parse_since(since) if since else None
    items: list = []
    partial = False
    for channel_ref in channels:
        try:
            entity = await resolve_channel(client, channel_ref)
        except ChannelResolutionError as e:
            items.append(
                ErrorEntry(channel=e.channel, error=e.code, detail=e.detail)
            )
            continue
        try:
            messages = await _collect_channel_messages(
                client, entity, channel_ref, limit_per_channel, query, since_dt
            )
        except FloodLimitExceeded as e:
            items.append(
                ErrorEntry(
                    channel=channel_ref,
                    error="flood_wait_exceeded",
                    detail=f"second flood wait would be {e.seconds}s",
                )
            )
            partial = True
            continue
        except Exception as e:
            log.exception("search_channels: unexpected error for %r", channel_ref)
            items.append(
                ErrorEntry(
                    channel=channel_ref, error="internal_error", detail=str(e)
                )
            )
            continue
        items.extend(messages)
    return ReadResult(items=items, partial=partial)


async def get_recent(channel: ChannelRef, limit: int = 30) -> ReadResult:
    """Return the most recent ``limit`` messages from a single channel."""
    client = await get_client()
    try:
        entity = await resolve_channel(client, channel)
    except ChannelResolutionError as e:
        return ReadResult(
            items=[ErrorEntry(channel=e.channel, error=e.code, detail=e.detail)]
        )
    try:
        messages = await _collect_channel_messages(
            client, entity, channel, limit, search=None, since_dt=None
        )
    except FloodLimitExceeded as e:
        return ReadResult(
            items=[
                ErrorEntry(
                    channel=channel,
                    error="flood_wait_exceeded",
                    detail=f"second flood wait would be {e.seconds}s",
                )
            ],
            partial=True,
        )
    except Exception as e:
        log.exception("get_recent: unexpected error for %r", channel)
        return ReadResult(
            items=[
                ErrorEntry(channel=channel, error="internal_error", detail=str(e))
            ]
        )
    return ReadResult(items=messages)


def _send_link(chat: ChannelRef, first_msg_id: int) -> Optional[str]:
    if isinstance(chat, str) and chat.startswith("@") and len(chat) > 1:
        return f"https://t.me/{chat[1:]}/{first_msg_id}"
    return None


async def send_to_self(
    text: str, chat: ChannelRef = "me", tag: Optional[str] = None
) -> SendResult:
    """Send ``text`` to ``chat``, splitting into multiple messages if needed.

    Caller contract: ``text`` is already valid MarkdownV2 (server does not
    escape body). Only the tag is escaped by ``prepend_tag``. ``parse_mode``
    is always ``"MarkdownV2"``. Returns a ``SendResult`` listing one id per
    delivered chunk; ``partial=True`` when delivery stopped after a second
    FloodWaitError mid-batch.
    """
    client = await get_client()
    if tag:
        text = prepend_tag(text, tag)
    chunks = split_for_telegram(text)
    message_ids: list[int] = []
    partial = False
    for chunk in chunks:
        async def factory(_chunk=chunk):
            return await client.send_message(chat, _chunk, parse_mode="MarkdownV2")

        try:
            sent = await with_flood_retry(factory, log)
        except FloodLimitExceeded:
            partial = True
            break
        message_ids.append(sent.id)
    link = _send_link(chat, message_ids[0]) if message_ids else None
    return SendResult(chat=chat, message_ids=message_ids, link=link, partial=partial)
