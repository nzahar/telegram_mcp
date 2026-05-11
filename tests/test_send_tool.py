"""Tests for tg_mcp.tools.send_to_self."""

from __future__ import annotations

import pytest

from tg_mcp.formatting import TELEGRAM_MESSAGE_LIMIT
from tg_mcp.tools import send_to_self

from tests.conftest import FakeClient, FakeSentMessage


class TestSingleChunk:
    async def test_short_text_to_me_returns_one_id_no_link(self, fake_client):
        client = fake_client(FakeClient())

        result = await send_to_self("hello", chat="me")

        assert result.message_ids == [1001]
        assert result.link is None
        assert result.partial is False
        assert result.chat == "me"
        assert len(client.send_calls) == 1
        chat, text, parse_mode = client.send_calls[0]
        assert chat == "me"
        assert text == "hello"
        assert parse_mode == "MarkdownV2"

    async def test_text_passes_through_un_escaped(self, fake_client):
        client = fake_client(FakeClient())
        body = "*bold* and _italic_"

        await send_to_self(body, chat="me")

        assert client.send_calls[0][1] == body

    async def test_tag_is_prepended_and_escaped(self, fake_client):
        client = fake_client(FakeClient())

        await send_to_self("body", chat="me", tag="news")

        sent_text = client.send_calls[0][1]
        assert sent_text.startswith("\\#news\n\nbody")

    async def test_public_chat_returns_link_for_first_message(self, fake_client):
        client = fake_client(
            FakeClient(send_behaviour=[FakeSentMessage(id=555)])
        )

        result = await send_to_self("hi", chat="@public_chan")

        assert result.message_ids == [555]
        assert result.link == "https://t.me/public_chan/555"

    async def test_mixed_case_username_link_is_lowercased(self, fake_client):
        """_send_link must lowercase the @username segment so the link matches
        what Telethon's resolve path returns (entity.username is always lower)."""
        client = fake_client(
            FakeClient(send_behaviour=[FakeSentMessage(id=42)])
        )

        result = await send_to_self("hi", chat="@MixedCaseChan")

        assert result.link == "https://t.me/mixedcasechan/42"

    async def test_at_only_username_produces_no_link(self, fake_client):
        """A bare '@' with nothing after it must not produce a link."""
        client = fake_client(FakeClient())

        result = await send_to_self("hi", chat="@")

        assert result.link is None

    async def test_numeric_chat_id_returns_no_link(self, fake_client):
        client = fake_client(FakeClient())

        result = await send_to_self("hi", chat=987654321)

        assert result.link is None
        assert result.chat == 987654321


class TestMultiChunk:
    async def test_long_text_splits_into_multiple_sends(self, fake_client):
        client = fake_client(FakeClient())
        # Three paragraphs each just under-limit so split produces 3 messages.
        para = "x" * (TELEGRAM_MESSAGE_LIMIT - 10)
        text = "\n\n".join([para, para, para])

        result = await send_to_self(text, chat="me")

        assert len(client.send_calls) == 3
        assert len(result.message_ids) == 3
        assert result.partial is False

    async def test_link_uses_first_message_id_only(self, fake_client):
        client = fake_client(
            FakeClient(
                send_behaviour=[
                    FakeSentMessage(id=100),
                    FakeSentMessage(id=101),
                    FakeSentMessage(id=102),
                ]
            )
        )
        para = "x" * (TELEGRAM_MESSAGE_LIMIT - 10)
        text = "\n\n".join([para, para, para])

        result = await send_to_self(text, chat="@somechan")

        assert result.message_ids == [100, 101, 102]
        assert result.link == "https://t.me/somechan/100"


class TestFloodHandling:
    async def test_single_flood_then_retry_succeeds(
        self, fake_client, fast_flood_retry, flood
    ):
        client = fake_client(
            FakeClient(send_behaviour=[flood(3), FakeSentMessage(id=42)])
        )

        result = await send_to_self("hi", chat="me")

        assert result.message_ids == [42]
        assert result.partial is False

    async def test_double_flood_marks_partial(
        self, fake_client, fast_flood_retry, flood
    ):
        # Two chunks; on the first chunk both attempts flood -> partial.
        client = fake_client(
            FakeClient(send_behaviour=[flood(5), flood(5)])
        )
        long_text = "\n\n".join(["x" * (TELEGRAM_MESSAGE_LIMIT - 10)] * 2)

        result = await send_to_self(long_text, chat="me")

        assert result.partial is True
        assert result.message_ids == []
        assert result.link is None

    async def test_double_flood_after_first_chunk_keeps_partial_ids(
        self, fake_client, fast_flood_retry, flood
    ):
        # First chunk sends OK (id=10), second chunk floods twice -> partial=True
        # but message_ids includes the delivered first chunk.
        client = fake_client(
            FakeClient(
                send_behaviour=[FakeSentMessage(id=10), flood(2), flood(2)]
            )
        )
        long_text = "\n\n".join(["x" * (TELEGRAM_MESSAGE_LIMIT - 10)] * 2)

        result = await send_to_self(long_text, chat="me")

        assert result.partial is True
        assert result.message_ids == [10]


class TestEdgeCases:
    async def test_empty_text_sends_nothing_returns_empty_ids(self, fake_client):
        """Empty text produces no chunks — nothing is sent, ids list is empty."""
        client = fake_client(FakeClient())

        result = await send_to_self("", chat="me")

        assert result.message_ids == []
        assert result.partial is False
        assert result.link is None
        assert len(client.send_calls) == 0

    async def test_tag_only_no_body(self, fake_client):
        """tag with empty body: prepend_tag still creates a header; message is sent."""
        client = fake_client(FakeClient())

        result = await send_to_self("", chat="me", tag="daily")

        # prepend_tag("", "daily") = "\\#daily\n\n" which split_for_telegram returns
        # as a single non-empty chunk.
        assert len(result.message_ids) == 1
        assert result.partial is False
        sent_text = client.send_calls[0][1]
        assert "\\#daily" in sent_text

    async def test_tag_with_multiple_leading_hashes(self, fake_client):
        """Tags like '#####news' strip all leading '#' and produce exactly one '#' in output."""
        client = fake_client(FakeClient())

        await send_to_self("body", chat="me", tag="#####news")

        sent_text = client.send_calls[0][1]
        first_line = sent_text.split("\n\n", 1)[0]
        # Only the normalised #news, escaped as \\#news.
        assert first_line == "\\#news"

    async def test_no_tag_text_sent_verbatim(self, fake_client):
        """Without a tag, the body reaches Telegram exactly as provided (caller's MarkdownV2)."""
        client = fake_client(FakeClient())
        body = "*bold* _italic_ [link](https://t.me/x)"

        await send_to_self(body, chat="me")

        assert client.send_calls[0][1] == body
