"""Тесты backend/reports.py::resolve_report_period — расчёт персонального
отчётного периода автора (день начала может отличаться от 1-го числа)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import reports  # noqa: E402


def _ts(year, month, day, hour=12):
    return time.mktime((year, month, day, hour, 0, 0, 0, 0, -1))


class TestResolveReportPeriod(unittest.TestCase):
    def test_start_day_one_is_plain_calendar_month(self):
        self.assertEqual(reports.resolve_report_period(1, _ts(2026, 9, 1)), (2026, 9))
        self.assertEqual(reports.resolve_report_period(1, _ts(2026, 9, 30)), (2026, 9))

    def test_default_start_day_zero_also_plain_calendar_month(self):
        """start_day <= 1 — то же самое, что и 1 (обычный календарный месяц),
        сохраняем совместимость на случай, если где-то передадут 0."""
        self.assertEqual(reports.resolve_report_period(0, _ts(2026, 9, 15)), (2026, 9))

    def test_custom_start_day_after_boundary(self):
        """start_day=15: 20 сентября (после 15-го) — это уже период "2026-09"."""
        self.assertEqual(reports.resolve_report_period(15, _ts(2026, 9, 20)), (2026, 9))

    def test_custom_start_day_before_boundary_belongs_to_previous_period(self):
        """10 сентября (до 15-го) — ещё предыдущий период, начавшийся 15 августа."""
        self.assertEqual(reports.resolve_report_period(15, _ts(2026, 9, 10)), (2026, 8))

    def test_custom_start_day_exactly_on_boundary(self):
        """Ровно 15-е число — уже НОВЫЙ период (день >= start_day)."""
        self.assertEqual(reports.resolve_report_period(15, _ts(2026, 9, 15)), (2026, 9))

    def test_year_boundary_wraps_correctly(self):
        """5 января при start_day=15 — ещё период, начавшийся 15 декабря
        ПРОШЛОГО года, не текущего января."""
        self.assertEqual(reports.resolve_report_period(15, _ts(2026, 1, 5)), (2025, 12))

    def test_defaults_to_now_when_no_timestamp_given(self):
        year, month = reports.resolve_report_period(1)
        now = time.localtime()
        self.assertEqual((year, month), (now.tm_year, now.tm_mon))


if __name__ == "__main__":
    unittest.main()
