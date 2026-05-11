"""Tests for formatting primitives (escape, split, tag).

Server-side send tests live in test_send_tool.py (Slice 5).
"""

from __future__ import annotations

import pytest

from tg_mcp.formatting import (
    TELEGRAM_MESSAGE_LIMIT,
    _hard_split,
    _split_keeping_separators,
    escape_md_v2,
    prepend_tag,
    split_for_telegram,
)
import re


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

    def test_text_exactly_at_limit_returns_single_chunk(self):
        """Text whose length == limit must be returned as a single chunk, not split."""
        text = "a" * TELEGRAM_MESSAGE_LIMIT
        chunks = split_for_telegram(text)
        assert chunks == [text]

    def test_text_one_over_limit_splits(self):
        """Text one character over the limit must produce two chunks."""
        text = "a" * (TELEGRAM_MESSAGE_LIMIT + 1)
        chunks = split_for_telegram(text)
        assert len(chunks) == 2
        assert all(len(c) <= TELEGRAM_MESSAGE_LIMIT for c in chunks)
        assert "".join(chunks) == text

    def test_long_sentence_with_only_commas_hard_splits(self):
        """Sentence with no .!? terminators cannot be split by sentence regex;
        falls back to hard-split by character."""
        # A very long "sentence" using only commas — _SENTENCE_SPLIT_RE won't match.
        text = ("word, " * 200).rstrip(", ")  # ~1199 chars
        limit = 100
        chunks = split_for_telegram(text, limit=limit)
        assert all(len(c) <= limit for c in chunks)
        # All original characters must be present (order preserved, join reconstructs).
        assert "".join(chunks) == text

    def test_unicode_boundary_does_not_corrupt_multibyte_chars(self):
        """Hard split must not cut inside a multi-byte character sequence."""
        # Each emoji is 1 Unicode code point but may be several bytes; str slicing
        # by index is safe in Python (it works on code points, not bytes).
        # We verify the character count is exactly right at boundaries.
        text = "\U0001f600" * 600  # 600 emoji, each 1 codepoint, 4 UTF-8 bytes
        limit = 100
        chunks = split_for_telegram(text, limit=limit)
        assert all(len(c) <= limit for c in chunks)
        assert "".join(chunks) == text

    def test_paragraph_separator_preserved_in_reconstruction(self):
        """Content of each paragraph must be fully represented across chunks."""
        p1 = "Alpha " * 50  # 300 chars
        p2 = "Beta " * 50   # 250 chars
        p3 = "Gamma " * 50  # 300 chars
        text = f"{p1}\n\n{p2}\n\n{p3}"
        chunks = split_for_telegram(text, limit=400)
        joined = "\n\n".join(chunks) if len(chunks) > 1 else chunks[0]
        # All three content blocks must be somewhere in the output.
        assert p1.strip() in "".join(chunks)
        assert p2.strip() in "".join(chunks)
        assert p3.strip() in "".join(chunks)


class TestHardSplitEscapePairDefense:
    """_hard_split must never leave a dangling backslash at a chunk boundary."""

    def test_boundary_on_single_trailing_backslash_shifts_to_next_chunk(self):
        # 4-char limit: "abc\" splits naively as ["abc\", "x"]
        # The trailing odd backslash must move to the next chunk.
        text = r"abc\x"  # raw string: a b c \ x  (5 chars)
        chunks = _hard_split(text, limit=4)
        assert all(len(c) <= 4 for c in chunks)
        # Chunk boundary must not end on a lone backslash.
        assert not chunks[0].endswith("\\") or chunks[0].endswith("\\\\"), (
            f"dangling backslash in chunk 0: {chunks[0]!r}"
        )
        # Reconstruction is lossless.
        assert "".join(chunks) == text

    def test_boundary_on_even_backslash_run_not_shifted(self):
        # Even run of backslashes at boundary is fine — they are escape pairs.
        # "aa\\" fits in 4 chars; second chunk is "bb".
        text = "aa\\\\bb"  # a a \ \ b b (6 chars)
        chunks = _hard_split(text, limit=4)
        assert "".join(chunks) == text
        # First chunk should not have been trimmed.
        assert chunks[0] == "aa\\\\"

    def test_backslash_at_limit_boundary_reconstruction_is_lossless(self):
        # Construct a string where the naive split falls exactly on a lone backslash.
        # limit=5: "aaaa\" (5 chars) -> shifts \ to next chunk.
        text = "aaaa\\" + "bbbb"  # 9 chars
        chunks = _hard_split(text, limit=5)
        assert "".join(chunks) == text
        for c in chunks:
            assert len(c) <= 5

    def test_no_backslashes_passes_through_unchanged(self):
        text = "abcdefgh"
        chunks = _hard_split(text, limit=4)
        assert chunks == ["abcd", "efgh"]

    def test_all_backslashes_splits_in_even_pairs(self):
        # 8 backslashes at limit=4: splits as ["\\\\", "\\\\"] — both even, no shift needed.
        text = "\\" * 8
        chunks = _hard_split(text, limit=4)
        assert "".join(chunks) == text
        assert all(len(c) <= 4 for c in chunks)


class TestSentenceSplitterWhitespacePreservation:
    """split_for_telegram's sentence-tier path must preserve original whitespace."""

    def test_newline_between_sentences_not_collapsed_to_space(self):
        # Build a long paragraph with a newline between two sentences.
        # The paragraph exceeds the limit; sentence splitting is forced.
        # The newline must survive in the output — it must not become " ".
        sentence_a = "A" * 60 + ". "  # 62 chars, ends at sentence boundary
        sentence_b = "\n" + "B" * 60 + "."  # 62 chars, starts with newline
        text = sentence_a + sentence_b  # 124 chars total
        chunks = split_for_telegram(text, limit=70)
        # Reconstruction must preserve the newline.
        joined = "".join(chunks)
        assert "\n" in joined, (
            "newline between sentences was collapsed; "
            f"chunks={chunks!r}"
        )

    def test_multiple_spaces_between_sentences_are_preserved(self):
        # Two spaces after a period must survive through sentence-level splitting.
        sentence_a = "X" * 60 + ".  "  # two trailing spaces
        sentence_b = "Y" * 60 + "."
        text = sentence_a + sentence_b
        chunks = split_for_telegram(text, limit=70)
        joined = "".join(chunks)
        # The two-space gap should appear somewhere in the reconstruction.
        assert ".  " in joined or joined == text, (
            f"double space collapsed; joined={joined!r}"
        )

    def test_split_keeping_separators_reconstructs_exactly(self):
        # Unit test for _split_keeping_separators directly:
        # splitting then joining with "" must reproduce the original string.
        text = "Hello world. Foo bar! Baz qux? Last."
        boundary = re.compile(r"(?<=[.!?])\s+")
        parts = _split_keeping_separators(text, boundary)
        assert "".join(parts) == text

    def test_split_keeping_separators_newline_in_separator(self):
        # Ensure that newline separators (not just spaces) are included in the
        # preceding segment so concatenation with "" is lossless.
        text = "Sentence one.\nSentence two."
        boundary = re.compile(r"(?<=[.!?])\s+")
        parts = _split_keeping_separators(text, boundary)
        assert "".join(parts) == text
        # The first part should include the trailing "\n".
        assert parts[0].endswith("\n"), f"separator not retained: {parts[0]!r}"


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
