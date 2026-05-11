from __future__ import annotations

from datetime import datetime
from typing import Optional, Union

from pydantic import BaseModel, Field


ChannelRef = Union[str, int]
"""Channel reference accepted by every tool: ``@username`` or numeric chat_id.

Defined here so callers and the client module reference the same alias.
:mod:`tg_mcp.client` re-exports it for backwards-compatibility.
"""


class Message(BaseModel):
    """A single Telegram message returned by read tools."""

    channel: ChannelRef = Field(
        description="Channel identifier as passed by the caller (@username or numeric chat_id)."
    )
    id: int = Field(description="Telegram message id.")
    date: datetime = Field(description="Message date in UTC.")
    text: str = Field(description="Message text. Empty string for media-only messages.")
    link: Optional[str] = Field(
        default=None,
        description=(
            "Public link of the form https://t.me/<username>/<id>. "
            "None for non-public chats (numeric chat_id, Saved Messages)."
        ),
    )
    views: Optional[int] = Field(
        default=None,
        description="View count. None for non-channel chats (e.g. groups).",
    )


class ErrorEntry(BaseModel):
    """Per-channel error returned alongside Messages from a read tool."""

    channel: ChannelRef = Field(
        description="Channel identifier as passed by the caller."
    )
    error: str = Field(
        description=(
            "Short machine-readable error type "
            "(channel_not_found, channel_private, flood_wait_exceeded, internal_error)."
        )
    )
    detail: Optional[str] = Field(
        default=None, description="Human-readable detail. May be None."
    )


class ReadResult(BaseModel):
    """Result of a read tool (``search_channels`` or ``get_recent``)."""

    items: list[Union[Message, ErrorEntry]] = Field(
        description=(
            "Mixed list of successful messages and per-channel errors. "
            "Order: channels are processed in the order passed in."
        )
    )
    partial: bool = Field(
        default=False,
        description=(
            "True when at least one channel was abandoned after a second "
            "FloodWaitError. Items from that channel are absent or incomplete."
        ),
    )


class SendResult(BaseModel):
    """Result of send_to_self."""

    chat: ChannelRef = Field(description="Chat identifier as passed by the caller.")
    message_ids: list[int] = Field(
        description="Message ids of the sent piece(s). Multi-message when text was split."
    )
    link: Optional[str] = Field(
        default=None,
        description=(
            "Public link to the first sent message when chat is a public @username. "
            "None for Saved Messages or numeric chat_id."
        ),
    )
    partial: bool = Field(
        default=False,
        description="True when not all parts were delivered (e.g. second FloodWait).",
    )
