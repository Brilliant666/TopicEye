from datetime import date, datetime

from app.services.daily_report import _day_window, _local_window_to_utc_naive, _normalize_edition


def test_snapshot_window_uses_start_of_target_day_to_cutoff():
    start, end = _day_window(
        date(2026, 5, 27),
        datetime(2026, 5, 27, 12, 0, 30),
        "noon",
    )

    assert start == datetime(2026, 5, 27, 0, 0, 0)
    assert end == datetime(2026, 5, 27, 12, 0, 30)


def test_final_window_covers_full_target_day():
    start, end = _day_window(date(2026, 5, 27), None, "final")

    assert start == datetime(2026, 5, 27, 0, 0, 0)
    assert end == datetime(2026, 5, 27, 23, 59, 59)


def test_past_date_defaults_to_final_edition():
    assert _normalize_edition(None, date(2020, 1, 1), None) == "final"


def test_report_window_queries_utc_storage_range():
    start, end = _local_window_to_utc_naive(
        datetime(2026, 5, 27, 0, 0, 0),
        datetime(2026, 5, 27, 12, 0, 0),
    )

    assert start == datetime(2026, 5, 26, 16, 0, 0)
    assert end == datetime(2026, 5, 27, 4, 0, 0)
