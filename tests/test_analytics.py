"""Тесты backend/analytics.py — помесячная агрегация "обнаружено" (из
журнала действий) и "заблокировано" (из block_date, активные + архивные)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import analytics  # noqa: E402


def _month_ago_ts(months_ago):
    """Unix-время примерно N месяцев назад (по 30 дней — этого достаточно
    для тестов на группировку по месяцу, не нужна календарная точность)."""
    return time.time() - months_ago * 30 * 86400


def _date_months_ago(months_ago):
    return time.strftime("%Y-%m-%d", time.localtime(_month_ago_ts(months_ago)))


class TestMonthKey(unittest.TestCase):
    def test_from_timestamp(self):
        ts = time.mktime(time.strptime("2026-03-15", "%Y-%m-%d"))
        self.assertEqual(analytics._month_key(ts), "2026-03")

    def test_from_date_string(self):
        self.assertEqual(analytics._month_key("2026-03-15"), "2026-03")

    def test_empty_returns_none(self):
        self.assertIsNone(analytics._month_key(""))
        self.assertIsNone(analytics._month_key(None))

    def test_garbage_string_returns_none(self):
        self.assertIsNone(analytics._month_key("не дата"))


class TestDomain(unittest.TestCase):
    def test_extracts_domain(self):
        self.assertEqual(analytics._domain("https://example.com/page"), "example.com")

    def test_strips_www(self):
        self.assertEqual(analytics._domain("https://www.example.com/page"), "example.com")

    def test_invalid_url_returns_empty(self):
        self.assertEqual(analytics._domain("не ссылка"), "")


class TestLastNMonths(unittest.TestCase):
    def test_returns_n_months_ascending(self):
        months = analytics._last_n_months(3, from_month="2026-03")
        self.assertEqual(months, ["2026-01", "2026-02", "2026-03"])

    def test_handles_year_boundary(self):
        months = analytics._last_n_months(3, from_month="2026-01")
        self.assertEqual(months, ["2025-11", "2025-12", "2026-01"])


class TestDetectedPerMonth(unittest.TestCase):
    def test_counts_only_add_to_blocking_actions(self):
        log = [
            {"ts": time.time(), "action": "добавил в блокировку", "details": "т (https://a.test/1)"},
            {"ts": time.time(), "action": "вошёл в систему", "details": ""},
        ]
        result = analytics.detected_per_month(log, months=1)
        self.assertEqual(result["counts"], [1])

    def test_groups_by_correct_month(self):
        log = [
            {"ts": _month_ago_ts(0), "action": "добавил в блокировку", "details": "т (https://a.test/1)"},
            {"ts": _month_ago_ts(1), "action": "добавил в блокировку", "details": "т (https://a.test/2)"},
        ]
        result = analytics.detected_per_month(log, months=2)
        self.assertEqual(len(result["months"]), 2)
        self.assertEqual(sum(result["counts"]), 2)

    def test_missing_months_show_zero_not_skipped(self):
        """Непрерывный ряд месяцев — если за месяц данных не было, там
        честный ноль, а не выпадающая точка на графике."""
        log = [{"ts": time.time(), "action": "добавил в блокировку", "details": "т (https://a.test/1)"}]
        result = analytics.detected_per_month(log, months=6)
        self.assertEqual(len(result["months"]), 6)
        self.assertEqual(len(result["counts"]), 6)
        self.assertEqual(result["counts"].count(0), 5)

    def test_extracts_domain_from_details_for_top_domains(self):
        log = [
            {"ts": time.time(), "action": "добавил в блокировку", "details": "т1 (https://pirate.test/a)"},
            {"ts": time.time(), "action": "добавил в блокировку", "details": "т2 (https://pirate.test/b)"},
            {"ts": time.time(), "action": "добавил в блокировку", "details": "т3 (https://other.test/c)"},
        ]
        result = analytics.detected_per_month(log, months=1)
        domains = {d["domain"]: d["count"] for d in result["top_domains"]}
        self.assertEqual(domains["pirate.test"], 2)
        self.assertEqual(domains["other.test"], 1)

    def test_total_all_time_not_limited_by_months_window(self):
        log = [
            {"ts": _month_ago_ts(0), "action": "добавил в блокировку", "details": "т (https://a.test/1)"},
            {"ts": _month_ago_ts(20), "action": "добавил в блокировку", "details": "т (https://a.test/2)"},
        ]
        result = analytics.detected_per_month(log, months=3)
        self.assertEqual(result["total_all_time"], 2)  # оба учтены, даже второй далеко за пределами окна в 3 месяца


class TestBlockedPerMonth(unittest.TestCase):
    def test_counts_active_blocked_cases(self):
        cases = [{"first_appeal_decision": "заблокировано", "block_date": _date_months_ago(0)}]
        result = analytics.blocked_per_month(cases, [], months=1)
        self.assertEqual(result["counts"], [1])

    def test_counts_needs_resend_blocked_case_too(self):
        """Дело заблокировано, но needs_resend уже встал (ссылка ожила) —
        факт блокировки в этом месяце всё равно учитывается."""
        cases = [{"first_appeal_decision": "заблокировано", "needs_resend": True, "block_date": _date_months_ago(0)}]
        result = analytics.blocked_per_month(cases, [], months=1)
        self.assertEqual(result["counts"], [1])

    def test_ignores_non_blocked_cases(self):
        cases = [{"block_date": _date_months_ago(0)}]  # ничего не заблокировано
        result = analytics.blocked_per_month(cases, [], months=1)
        self.assertEqual(result["counts"], [0])

    def test_counts_archived_cases_too(self):
        """Ключевая проверка: архивация после завершения месячного отчёта
        не должна «съедать» историю из статистики."""
        archived = [{"block_date": _date_months_ago(0)}]
        result = analytics.blocked_per_month([], archived, months=1)
        self.assertEqual(result["counts"], [1])

    def test_status_breakdown_reflects_outcome_buckets(self):
        """Общего поля «Статус» больше нет — разбивка теперь по факту:
        заблокировано (и держится) / нужна повторная подача / в процессе."""
        cases = [
            {"block_date": ""},  # ничего не определено — «в процессе»
            {"block_date": ""},
            {"first_appeal_decision": "заблокировано", "block_date": _date_months_ago(0)},  # держится
            {"first_appeal_decision": "заблокировано", "needs_resend": True, "block_date": _date_months_ago(0)},  # нужна повторная
        ]
        result = analytics.blocked_per_month(cases, [], months=1)
        self.assertEqual(result["status_breakdown"]["в процессе"], 2)
        self.assertEqual(result["status_breakdown"]["заблокировано"], 1)
        self.assertEqual(result["status_breakdown"]["нужна повторная подача"], 1)


class TestSpreadDynamics(unittest.TestCase):
    def test_combines_detected_and_blocked_series(self):
        log = [{"ts": time.time(), "action": "добавил в блокировку", "details": "т (https://a.test/1)"}]
        cases = [{"url": "https://a.test/1", "first_appeal_decision": "заблокировано", "block_date": _date_months_ago(0)}]
        result = analytics.spread_dynamics(log, cases, [], months=1)
        self.assertEqual(result["detected_counts"], [1])
        self.assertEqual(result["blocked_counts"], [1])

    def test_median_delay_computed_when_both_dates_known(self):
        added_ts = _month_ago_ts(1)
        log = [{"ts": added_ts, "action": "добавил в блокировку", "details": "т (https://a.test/1)"}]
        block_date = time.strftime("%Y-%m-%d", time.localtime(added_ts + 10 * 86400))  # заблокировано через 10 дней
        cases = [{"url": "https://a.test/1", "first_appeal_decision": "заблокировано", "block_date": block_date}]
        result = analytics.spread_dynamics(log, cases, [], months=2)
        self.assertIsNotNone(result["median_days_to_block"])
        self.assertAlmostEqual(result["median_days_to_block"], 10, delta=1)

    def test_median_delay_is_none_without_enough_data(self):
        result = analytics.spread_dynamics([], [], [], months=1)
        self.assertIsNone(result["median_days_to_block"])
        self.assertEqual(result["cases_with_known_delay"], 0)

    def test_negative_delay_excluded_as_bad_data(self):
        """Если дата блокировки почему-то раньше даты добавления (опечатка
        при вводе) — не учитываем такую запись, а не считаем «минус дни»."""
        added_ts = time.time()
        log = [{"ts": added_ts, "action": "добавил в блокировку", "details": "т (https://a.test/1)"}]
        block_date = time.strftime("%Y-%m-%d", time.localtime(added_ts - 30 * 86400))
        cases = [{"url": "https://a.test/1", "first_appeal_decision": "заблокировано", "block_date": block_date}]
        result = analytics.spread_dynamics(log, cases, [], months=1)
        self.assertEqual(result["cases_with_known_delay"], 0)


class TestApplyOverrides(unittest.TestCase):
    def test_override_replaces_auto_value(self):
        final, flags = analytics.apply_overrides(["2026-06", "2026-07"], [1, 2], {"2026-07": 99})
        self.assertEqual(final, [1, 99])
        self.assertEqual(flags, [False, True])

    def test_no_overrides_leaves_values_unchanged(self):
        final, flags = analytics.apply_overrides(["2026-06"], [5], {})
        self.assertEqual(final, [5])
        self.assertEqual(flags, [False])

    def test_override_can_be_zero(self):
        """0 — законное значение поправки (не путать с «поправки нет»)."""
        final, flags = analytics.apply_overrides(["2026-06"], [5], {"2026-06": 0})
        self.assertEqual(final, [0])
        self.assertEqual(flags, [True])

    def test_override_for_month_outside_series_is_ignored(self):
        final, flags = analytics.apply_overrides(["2026-06"], [5], {"2099-01": 100})
        self.assertEqual(final, [5])
        self.assertEqual(flags, [False])


if __name__ == "__main__":
    unittest.main()
