"""Tests for formatting primitives (escape, split, tag).

Server-side send tests live in test_send_tool.py (Slice 5).
"""

from __future__ import annotations

import pytest

from tg_mcp.formatting import (
    TELEGRAM_MESSAGE_LIMIT,
    escape_md_v2,
    prepend_tag,
    split_for_telegram,
)


class TestEscapeMdV2:
    def test_escapes_full_special_set(self):
        specials = r"_*[]()~`>#+-=|{}.!" + "\\"
        escaped = escape_md_v2(specials)
        # Every special must be preceded by a backslash, original char preserved.
        for ch in specials:
            assert f"\\{ch}" in escaped
        # Length doubles because every char gets a backslash partner.
        assert len(escaped) == 2 * len(specials)

    def test_plain_text_unchanged(self):
        assert escape_md_v2("hello world 123") == "hello world 123"

    def test_cyrillic_unchanged(self):
        assert escape_md_v2("привет мир") == "привет мир"

    def test_mixed(self):
        assert escape_md_v2("a.b") == "a\\.b"
        assert escape_md_v2("price: $5 (today)") == "price: $5 \\(today\\)"


class TestSplitForTelegram:
    def test_empty(self):
        assert split_for_telegram("") == []

    def test_short_text_single_chunk(self):
        assert split_for_telegram("short") == ["short"]

    def test_default_limit_is_4096(self):
        assert TELEGRAM_MESSAGE_LIMIT == 4096

    def test_split_by_paragraph(self):
        # Three paragraphs, 100 chars each; limit forces split.
        paragraphs = ["A" * 100, "B" * 100, "C" * 100]
        text = "\n\n".join(paragraphs)
        chunks = split_for_telegram(text, limit=120)
        assert all(len(c) <= 120 for c in chunks)
        # Reconstructed content must contain all original bytes.
        joined = "".join(chunks)
        for p in paragraphs:
            assert p in joined

    def test_paragraph_greedy_packing(self):
        # Two short paragraphs fit together, third forces a break.
        text = "p1\n\np2\n\np3longertext"
        chunks = split_for_telegram(text, limit=10)
        assert all(len(c) <= 10 for c in chunks)
        assert "p1" in chunks[0]

    def test_split_by_sentence_fallback(self):
        # Single paragraph, three sentences, no paragraph break can help.
        text = "First sentence. Second one here. Third end."
        chunks = split_for_telegram(text, limit=20)
        assert len(chunks) >= 2
        assert all(len(c) <= 20 for c in chunks)
        # Sentence terminator preserved at end of at least one chunk.
        assert any(c.endswith(".") for c in chunks)

    def test_hard_split_fallback(self):
        # Single very long token (no spaces, no punctuation).
        text = "x" * 1000
        chunks = split_for_telegram(text, limit=300)
        assert len(chunks) == 4  # 300+300+300+100
        assert all(len(c) <= 300 for c in chunks)
        assert "".join(chunks) == text

    def test_reaches_exactly_under_limit(self):
        text = ("paragraph\n\n" * 50).rstrip()
        chunks = split_for_telegram(text, limit=50)
        assert all(len(c) <= 50 for c in chunks)


class TestPrependTag:
    def test_tag_without_hash(self):
        assert prepend_tag("body", "news") == "\\#news\n\nbody"

    def test_tag_with_hash_normalised(self):
        # Leading # is stripped then re-added — exactly one # in output.
        assert prepend_tag("body", "#news") == prepend_tag("body", "news")

    def test_tag_special_chars_escaped(self):
        out = prepend_tag("body", "daily-news")
        # First line contains escaped dash.
        first_line = out.split("\n\n", 1)[0]
        assert first_line == "\\#daily\\-news"

    def test_body_passthrough_no_double_escape(self):
        # Caller-provided MarkdownV2 must reach Telegram intact.
        body = "*bold* and _italic_ with [link](https://t.me/a)"
        out = prepend_tag(body, "x")
        parts = out.split("\n\n", 1)
        assert parts[1] == body

    @pytest.mark.parametrize("tag", ["x", "#x", "##x"])
    def test_only_first_hash_treated_as_marker(self, tag):
        # lstrip("#") removes all leading #, leaving content "x"; output has one literal #.
        out = prepend_tag("b", tag)
        assert out.startswith("\\#x\n\n")
