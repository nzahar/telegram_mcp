"""Tests for tg_mcp.client.parse_since."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tg_mcp.client import parse_since


class TestRelative:
    @pytest.mark.parametrize(
        "value, unit_delta",
        [
            ("7d", timedelta(days=7)),
            ("1d", timedelta(days=1)),
            ("24h", timedelta(hours=24)),
            ("3h", timedelta(hours=3)),
            ("30m", timedelta(minutes=30)),
            ("1m", timedelta(minutes=1)),
        ],
    )
    def test_relative_units(self, value, unit_delta):
        before = datetime.now(timezone.utc) - unit_delta
        result = parse_since(value)
        after = datetime.now(timezone.utc) - unit_delta
        assert before - timedelta(seconds=2) <= result <= after + timedelta(seconds=2)
        assert result.tzinfo is not None

    def test_case_insensitive(self):
        a = parse_since("7D")
        b = parse_since("7d")
        assert abs((a - b).total_seconds()) < 1

    def test_whitespace_tolerated(self):
        result = parse_since("  7d  ")
        assert (datetime.now(timezone.utc) - result).days == 7


class TestIso:
    def test_iso_date_treated_as_utc_midnight(self):
        result = parse_since("2026-05-01")
        assert result == datetime(2026, 5, 1, tzinfo=timezone.utc)

    def test_iso_datetime_naive_treated_as_utc(self):
        result = parse_since("2026-05-01T12:00:00")
        assert result == datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)

    def test_iso_datetime_with_offset_preserved(self):
        result = parse_since("2026-05-01T15:00:00+03:00")
        assert result.utcoffset() == timedelta(hours=3)
        # Same instant as 12:00 UTC.
        assert result.astimezone(timezone.utc) == datetime(
            2026, 5, 1, 12, 0, tzinfo=timezone.utc
        )


class TestInvalid:
    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "yesterday",
            "7",
            "d7",
            "7y",
            "not-a-date",
            "2026-13-01",  # invalid month
        ],
    )
    def test_invalid_raises_value_error(self, value):
        with pytest.raises(ValueError):
            parse_since(value)

    def test_non_string_raises(self):
        with pytest.raises(ValueError):
            parse_since(None)  # type: ignore[arg-type]
