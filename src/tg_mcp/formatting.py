"""MarkdownV2 escaping, message splitting, and tag prepending."""

from __future__ import annotations

import re


TELEGRAM_MESSAGE_LIMIT = 4096

_MD_V2_SPECIALS = r"_*[]()~`>#+-=|{}.!\\"
_MD_V2_ESCAPE_RE = re.compile(f"([{re.escape(_MD_V2_SPECIALS)}])")


def escape_md_v2(text: str) -> str:
    """Escape Telegram MarkdownV2 special characters with a leading backslash."""
    return _MD_V2_ESCAPE_RE.sub(r"\\\1", text)


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _greedy_pack(parts: list[str], sep: str, limit: int) -> list[str]:
    """Greedily join parts with ``sep`` into chunks no longer than ``limit``.

    Parts already longer than ``limit`` pass through as their own chunk; the
    caller is responsible for splitting them at a finer granularity.
    """
    result: list[str] = []
    current = ""
    for p in parts:
        if not current:
            current = p
            continue
        candidate = f"{current}{sep}{p}"
        if len(candidate) <= limit:
            current = candidate
        else:
            result.append(current)
            current = p
    if current:
        result.append(current)
    return result


def _hard_split(text: str, limit: int) -> list[str]:
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def split_for_telegram(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split ``text`` into chunks each at most ``limit`` characters.

    Strategy, applied lazily:
      1. If ``text`` fits, return ``[text]``.
      2. Split by blank-line paragraphs and greedily repack.
      3. For chunks still too large, split each by sentence and repack.
      4. For sentences still too large, hard-split by character.
    """
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    paragraph_chunks = _greedy_pack(text.split("\n\n"), "\n\n", limit)

    result: list[str] = []
    for chunk in paragraph_chunks:
        if len(chunk) <= limit:
            result.append(chunk)
            continue
        sentences = [s for s in _SENTENCE_SPLIT_RE.split(chunk) if s]
        sentence_chunks = _greedy_pack(sentences, " ", limit)
        for sc in sentence_chunks:
            if len(sc) <= limit:
                result.append(sc)
            else:
                result.extend(_hard_split(sc, limit))
    return result


def prepend_tag(text: str, tag: str) -> str:
    """Prepend a ``#<tag>`` first line + blank line to ``text``.

    The tag is normalised (leading ``#`` stripped, then re-added) and escaped
    for MarkdownV2. ``text`` itself is passed through unchanged — the caller
    contract is that ``text`` is already valid MarkdownV2 (see README).
    """
    normalised = tag.lstrip("#")
    safe_tag = escape_md_v2(f"#{normalised}")
    return f"{safe_tag}\n\n{text}"
