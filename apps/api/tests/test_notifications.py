"""notifications/__init__.py's own formatting helpers -- no test here sends
a real email (get_notification_provider() falls back to
ConsoleNotificationProvider when RESEND_API_KEY is unset, but even that
isn't exercised here; this is purely the pure-function formatting logic).
"""

from datetime import datetime, timezone

from app.notifications import _format_time_range


def test_format_time_range_is_human_readable_and_labeled_utc():
    start = datetime(2026, 9, 2, 2, 30, tzinfo=timezone.utc)
    end = datetime(2026, 9, 2, 3, 0, tzinfo=timezone.utc)

    result = _format_time_range(start, end)

    assert result == "Wednesday, September 2, 2026 · 2:30 AM - 3:00 AM UTC"


def test_format_time_range_has_no_leading_zero_on_single_digit_day():
    start = datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)

    result = _format_time_range(start, end)

    assert "January 5, 2026" in result
    assert "January 05" not in result


def test_format_time_range_handles_noon_and_midnight_hour_without_stripping_the_1():
    start = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)

    result = _format_time_range(start, end)

    assert "12:00 PM" in result
    assert "1:00 PM" in result
