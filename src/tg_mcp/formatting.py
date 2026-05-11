"""MarkdownV2 escaping, message splitting, and tag prepending."""

from __future__ import annotations

import re


TELEGRAM_MESSAGE_LIMIT = 4096

_MD_V2_SPECIALS = r"_*[]()~`>#+-=|{}.!\\"
_MD_V2_ESCAPE_RE = re.compile(f"([{re.escape(_MD_V2_SPECIALS)}])")


def escape_md_v2(text: str) -> str:
    """Escape Telegram MarkdownV2 special characters with a leading backslash."""
    return _MD_V2_ESCAPE_RE.sub(r"\\\1", text)


_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


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


def _split_keeping_separators(text: str, boundary: re.Pattern[str]) -> list[str]:
    """Split text on ``boundary``; each emitted segment retains its trailing
    separator so concatenation with ``""`` reconstructs the original text.

    Used for sentence-level splitting so mid-paragraph newlines and other
    whitespace are preserved across chunks instead of being collapsed to a
    single space.
    """
    segments: list[str] = []
    last = 0
    for m in boundary.finditer(text):
        segments.append(text[last : m.end()])
        last = m.end()
    if last < len(text) or not segments:
        segments.append(text[last:])
    return segments


def _pack_preserving(parts: list[str], limit: int) -> list[str]:
    """Like :func:`_greedy_pack` but joins with ``""`` because each part
    already carries its own trailing separator."""
    result: list[str] = []
    current = ""
    for p in parts:
        if not current:
            current = p
            continue
        candidate = current + p
        if len(candidate) <= limit:
            current = candidate
        else:
            result.append(current)
            current = p
    if current:
        result.append(current)
    return result


def _hard_split(text: str, limit: int) -> list[str]:
    """Hard-split ``text`` into chunks of at most ``limit`` characters.

    Defends against breaking a MarkdownV2 escape pair: if a chunk would end on
    an odd run of trailing backslashes, the trailing ``\\`` is pushed to the
    next chunk so neither chunk presents a dangling escape character to
    Telegram's parser.
    """
    chunks = [text[i : i + limit] for i in range(0, len(text), limit)]
    for i in range(len(chunks) - 1):
        chunk = chunks[i]
        trailing = 0
        while trailing < len(chunk) and chunk[len(chunk) - 1 - trailing] == "\\":
            trailing += 1
        if trailing % 2 == 1:
            chunks[i] = chunk[:-1]
            chunks[i + 1] = "\\" + chunks[i + 1]
    return [c for c in chunks if c]


def split_for_telegram(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split ``text`` into chunks each at most ``limit`` characters.

    Strategy, applied lazily:
      1. If ``text`` fits, return ``[text]``.
      2. Split by blank-line paragraphs and greedily repack.
      3. For chunks still too large, split by sentence (preserving the
         original whitespace between sentences) and repack.
      4. For sentences still too large, hard-split by character (preserving
         MarkdownV2 escape pairs at chunk boundaries).
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
        sentence_parts = _split_keeping_separators(chunk, _SENTENCE_BOUNDARY_RE)
        sentence_chunks = _pack_preserving(sentence_parts, limit)
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
