import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402
from backend import link_check  # noqa: E402


class TestIsDue(unittest.TestCase):
    def setUp(self):
        self.now = time.time()

    def _days_ago(self, days):
        return time.strftime("%Y-%m-%d", time.localtime(self.now - days * 86400))

    def test_due_after_14_days_unchecked(self):
        case = {"petition_filed_at": self._days_ago(20), "link_checked_at": ""}
        self.assertTrue(link_check.is_due(case, self.now))

    def test_not_due_before_14_days(self):
        case = {"petition_filed_at": self._days_ago(5), "link_checked_at": ""}
        self.assertFalse(link_check.is_due(case, self.now))

    def test_exactly_14_days_is_due(self):
        case = {"petition_filed_at": self._days_ago(14), "link_checked_at": ""}
        self.assertTrue(link_check.is_due(case, self.now))

    def test_not_due_if_already_checked(self):
        case = {"petition_filed_at": self._days_ago(20), "link_checked_at": self.now - 100}
        self.assertFalse(link_check.is_due(case, self.now))

    def test_not_due_if_not_filed(self):
        case = {"petition_filed_at": "", "link_checked_at": ""}
        self.assertFalse(link_check.is_due(case, self.now))

    def test_malformed_date_does_not_crash(self):
        case = {"petition_filed_at": "не дата", "link_checked_at": ""}
        self.assertFalse(link_check.is_due(case, self.now))

    def test_recurs_after_daily_interval_passes(self):
        case = {
            "petition_filed_at": self._days_ago(20),
            "link_checked_at": self.now - 25 * 3600,  # проверяли 25 часов назад
            "link_check_interval": "day",
        }
        self.assertTrue(link_check.is_due(case, self.now))

    def test_does_not_recur_before_daily_interval_passes(self):
        case = {
            "petition_filed_at": self._days_ago(20),
            "link_checked_at": self.now - 5 * 3600,  # проверяли 5 часов назад
            "link_check_interval": "day",
        }
        self.assertFalse(link_check.is_due(case, self.now))

    def test_hourly_interval_recurs_sooner_than_daily(self):
        case = {
            "petition_filed_at": self._days_ago(20),
            "link_checked_at": self.now - 3700,  # чуть больше часа назад
            "link_check_interval": "hour",
        }
        self.assertTrue(link_check.is_due(case, self.now))

    def test_weekly_interval_does_not_recur_after_one_day(self):
        case = {
            "petition_filed_at": self._days_ago(30),
            "link_checked_at": self.now - 2 * 86400,  # 2 дня назад
            "link_check_interval": "week",
        }
        self.assertFalse(link_check.is_due(case, self.now))

    def test_monthly_interval_does_not_recur_after_one_week(self):
        case = {
            "petition_filed_at": self._days_ago(60),
            "link_checked_at": self.now - 7 * 86400,  # неделю назад
            "link_check_interval": "month",
        }
        self.assertFalse(link_check.is_due(case, self.now))

    def test_missing_interval_falls_back_to_daily_default(self):
        """Дело без явно выбранного интервала (например, старые записи,
        сохранённые до появления этой настройки) — по умолчанию раз в день."""
        case = {
            "petition_filed_at": self._days_ago(20),
            "link_checked_at": self.now - 25 * 3600,
            "link_check_interval": "",
        }
        self.assertTrue(link_check.is_due(case, self.now))

    def test_recurring_continues_indefinitely_not_just_once(self):
        """Ключевое отличие от прежнего поведения: проверка не
        останавливается после первого раза — только когда дело уходит из
        активной таблицы (это уже не забота is_due, а того, что
        наблюдатель просто не увидит архивированное дело)."""
        case = {"petition_filed_at": self._days_ago(100), "link_checked_at": self.now - 100000, "link_check_interval": "day"}
        self.assertTrue(link_check.is_due(case, self.now))  # третья, десятая — неважно какая по счёту проверка, всё ещё «созрело»

    # --- проверка дел «заблокировано» — привязка к дате блокировки, а не подачи ---
    def test_blocked_case_due_by_block_date_even_without_petition(self):
        """Дело могли заблокировать и без заявления в суд (например, через
        обычное обращение в РКН) — проверка всё равно должна работать,
        отталкиваясь от даты блокировки."""
        case = {"first_appeal_decision": "заблокировано", "block_date": self._days_ago(20), "petition_filed_at": "", "link_checked_at": ""}
        self.assertTrue(link_check.is_due(case, self.now))

    def test_blocked_case_not_due_before_14_days_after_block_date(self):
        case = {"first_appeal_decision": "заблокировано", "block_date": self._days_ago(5), "petition_filed_at": "", "link_checked_at": ""}
        self.assertFalse(link_check.is_due(case, self.now))

    def test_blocked_case_uses_block_date_not_older_petition_date(self):
        """Если дело когда-то подавалось, а потом было заблокировано —
        отсчёт для дальнейшего мониторинга идёт от даты блокировки, не от
        (более старой) даты подачи заявления."""
        case = {
            "first_appeal_decision": "заблокировано",
            "petition_filed_at": self._days_ago(60),  # заявление подавалось давно
            "block_date": self._days_ago(5),           # а заблокировали недавно
            "link_checked_at": "",
        }
        self.assertFalse(link_check.is_due(case, self.now))  # рано — 5 дней с блокировки, не 60 с заявления

    def test_non_blocked_case_ignores_block_date(self):
        """У дела, которое ещё ничем не заблокировано, c заполненным
        block_date по ошибке — отсчёт всё равно должен идти от даты
        подачи заявления."""
        case = {
            "block_date": self._days_ago(20),
            "petition_filed_at": self._days_ago(3),
            "link_checked_at": "",
        }
        self.assertFalse(link_check.is_due(case, self.now))  # 3 дня с подачи — рано, block_date тут не при чём

    def test_blocked_without_block_date_never_falls_back_to_petition_date(self):
        """Регрессия на реальный найденный баг: решение «заблокировано»
        (на любом из трёх этапов) есть, а поле «Дата блокировки» ещё не
        заполнено — раньше код проваливался обратно к дате подачи
        заявления, и если она была старой (например, заявление подавалось
        ещё до того, как претензия подействовала), автоматика ошибочно
        включала needs_resend и снова открывала чекбокс заявления по уже
        закрытому делу. Теперь — просто не мониторим, пока block_date не
        заполнена, дата подачи заявления тут больше не при чём."""
        case = {
            "claim_decision": "заблокировано",
            "block_date": "",  # не заполнено
            "petition_filed_at": self._days_ago(30),  # старая дата — раньше именно она ошибочно использовалась
            "link_checked_at": "",
        }
        self.assertFalse(link_check.is_due(case, self.now))

    def test_uses_rkn_filed_at_if_no_petition(self):
        """Дело могли подать сразу в РКН, минуя суд (или заявление в суд
        подавалось так давно, что petition_filed_at не заполнено в этом
        деле) — обращение в РКН само по себе тоже должно запускать отсчёт."""
        case = {"rkn_filed_at": self._days_ago(15), "link_checked_at": ""}
        self.assertTrue(link_check.is_due(case, self.now))

    def test_uses_later_of_petition_and_rkn_dates(self):
        """Ключевое новое поведение: если РКН подано ПОЗЖЕ заявления в
        суд — 14 дней отсчитываются от даты РКН (более позднее событие),
        а не от уже устаревшей даты самого заявления."""
        case = {
            "petition_filed_at": self._days_ago(20),  # заявление подано давно
            "rkn_filed_at": self._days_ago(5),  # а в РКН обратились недавно
            "link_checked_at": "",
        }
        self.assertFalse(link_check.is_due(case, self.now))  # 5 дней с РКН — рано, хотя с заявления уже 20

    def test_petition_later_than_rkn_still_used_correctly(self):
        """И наоборот — если заявление в суд (переподача) случилось позже
        старого обращения в РКН, отсчёт идёт от заявления."""
        case = {
            "rkn_filed_at": self._days_ago(20),
            "petition_filed_at": self._days_ago(5),
            "link_checked_at": "",
        }
        self.assertFalse(link_check.is_due(case, self.now))

    def test_both_dates_old_enough_is_due(self):
        case = {
            "petition_filed_at": self._days_ago(30),
            "rkn_filed_at": self._days_ago(15),
            "link_checked_at": "",
        }
        self.assertTrue(link_check.is_due(case, self.now))  # позднейшая (РКН) дата уже больше 14 дней назад


    def test_still_available_after_petition_flags_needs_resend(self):
        case = {"url": "https://x.test"}
        patch = link_check.build_update_patch(case, "доступна", 12345.0)
        self.assertTrue(patch["needs_resend"])
        self.assertEqual(patch["link_status"], "доступна")

    def test_unavailable_after_petition_clears_needs_resend(self):
        case = {"url": "https://x.test"}
        patch = link_check.build_update_patch(case, "недоступна", 12345.0)
        self.assertFalse(patch["needs_resend"])

    def test_blocked_case_coming_back_up_still_flags_needs_resend(self):
        """Общего поля «Статус» больше нет — при возврате ссылки в
        доступность просто ставится needs_resend, какое именно из трёх
        решений поправить, решает сотрудник вручную."""
        case = {"first_appeal_decision": "заблокировано", "url": "https://x.test"}
        patch = link_check.build_update_patch(case, "доступна", 12345.0)
        self.assertTrue(patch["needs_resend"])
        self.assertNotIn("status", patch)  # такого поля больше не существует вовсе

    def test_blocked_case_staying_down_does_not_flag_needs_resend(self):
        case = {"first_appeal_decision": "заблокировано", "url": "https://x.test"}
        patch = link_check.build_update_patch(case, "недоступна", 12345.0)
        self.assertFalse(patch["needs_resend"])

    def test_blocked_via_any_of_three_stages_is_recognized(self):
        """is_blocked() — любой из трёх этапов, не только «первое обращение»."""
        self.assertTrue(link_check.is_blocked({"claim_decision": "заблокировано"}))
        self.assertTrue(link_check.is_blocked({"first_appeal_decision": "заблокировано"}))
        self.assertTrue(link_check.is_blocked({"repeat_appeal_decision": "заблокировано"}))
        self.assertFalse(link_check.is_blocked({"claim_decision": "отклонено"}))
        self.assertFalse(link_check.is_blocked({}))

    def test_appeal_failed_checks_first_and_repeat_stages_only(self):
        """appeal_failed() — намеренно НЕ смотрит на claim_decision:
        провал досудебной претензии означает «переходим к следующему
        этапу», а не «нужно переподавать то же самое обращение»."""
        self.assertTrue(link_check.appeal_failed({"first_appeal_decision": "отклонено"}))
        self.assertTrue(link_check.appeal_failed({"first_appeal_decision": "нет реакции"}))
        self.assertTrue(link_check.appeal_failed({"repeat_appeal_decision": "отклонено"}))
        self.assertFalse(link_check.appeal_failed({"claim_decision": "отклонено"}))
        self.assertFalse(link_check.appeal_failed({}))

    def test_anchor_uses_block_date_when_any_stage_is_blocked(self):
        """_anchor_date (через is_due) учитывает любой из трёх этапов, не
        только первое обращение."""
        case = {
            "repeat_appeal_decision": "заблокировано",
            "block_date": self._days_ago(20), "petition_filed_at": self._days_ago(3),
            "link_checked_at": "",
        }
        self.assertTrue(link_check.is_due(case, self.now))  # берёт block_date (20 дней), не petition_filed_at (3 дня)

    def test_anchor_uses_latest_of_all_four_filing_dates(self):
        """Ключевое новое поведение: повторная подача (в суд ИЛИ в РКН)
        имеет свою отдельную дату, отличную от первой — отсчёт всегда
        идёт от самой последней из всех четырёх известных дат."""
        case = {
            "petition_filed_at": self._days_ago(60),        # первое заявление — давно
            "rkn_filed_at": self._days_ago(50),              # первое обращение в РКН — тоже давно
            "repeat_petition_filed_at": self._days_ago(20),  # повторное заявление — не очень давно
            "repeat_rkn_filed_at": self._days_ago(3),        # повторное обращение в РКН — совсем недавно
            "link_checked_at": "",
        }
        self.assertFalse(link_check.is_due(case, self.now))  # 3 дня с последнего действия — рано

    def test_anchor_uses_latest_even_if_repeat_dates_are_older(self):
        case = {
            "petition_filed_at": self._days_ago(3),          # первое заявление — недавно (переподали)
            "repeat_rkn_filed_at": self._days_ago(60),        # повторное обращение в РКН было давно
            "link_checked_at": "",
        }
        self.assertFalse(link_check.is_due(case, self.now))  # берёт максимум — 3 дня с petition_filed_at


class TestCheck(unittest.TestCase):
    def setUp(self):
        self._orig_delay = link_check.RETRY_DELAY_SEC
        link_check.RETRY_DELAY_SEC = 0  # не ждать реальные секунды в тестах

    def tearDown(self):
        link_check.RETRY_DELAY_SEC = self._orig_delay

    def test_status_200_is_reachable(self):
        with patch("requests.get", return_value=MagicMock(status_code=200)):
            status, ts = link_check.check("https://x.test")
        self.assertEqual(status, "доступна")

    def test_status_399_is_reachable(self):
        with patch("requests.get", return_value=MagicMock(status_code=308)):
            status, ts = link_check.check("https://x.test")
        self.assertEqual(status, "доступна")

    def test_status_404_is_unreachable(self):
        with patch("requests.get", return_value=MagicMock(status_code=404)):
            status, ts = link_check.check("https://x.test")
        self.assertEqual(status, "недоступна")

    def test_status_500_is_unreachable(self):
        with patch("requests.get", return_value=MagicMock(status_code=500)):
            status, ts = link_check.check("https://x.test")
        self.assertEqual(status, "недоступна")

    def test_timeout_is_unreachable(self):
        with patch("requests.get", side_effect=requests.exceptions.Timeout()):
            status, ts = link_check.check("https://x.test")
        self.assertEqual(status, "недоступна")

    def test_connection_error_is_unreachable(self):
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError()):
            status, ts = link_check.check("https://x.test")
        self.assertEqual(status, "недоступна")

    def test_returns_current_timestamp(self):
        before = time.time()
        with patch("requests.get", return_value=MagicMock(status_code=200)):
            _, ts = link_check.check("https://x.test")
        after = time.time()
        self.assertTrue(before <= ts <= after)

    def test_recovers_on_second_attempt_after_first_timeout(self):
        """Ключевая причина ретрая: единичный сетевой сбой на первой
        попытке не должен приводить к ложному «недоступна»."""
        responses = [requests.exceptions.Timeout(), MagicMock(status_code=200)]

        def side_effect(*a, **kw):
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with patch("requests.get", side_effect=side_effect) as mock_get:
            status, _ = link_check.check("https://x.test")
        self.assertEqual(status, "доступна")
        self.assertEqual(mock_get.call_count, 2)

    def test_unreachable_on_both_attempts_is_unavailable(self):
        with patch("requests.get", side_effect=requests.exceptions.Timeout()) as mock_get:
            status, _ = link_check.check("https://x.test")
        self.assertEqual(status, "недоступна")
        self.assertEqual(mock_get.call_count, 2)  # обе попытки были сделаны, не одна

    def test_reachable_on_first_attempt_does_not_retry(self):
        with patch("requests.get", return_value=MagicMock(status_code=200)) as mock_get:
            link_check.check("https://x.test")
        self.assertEqual(mock_get.call_count, 1)  # успех сразу — вторая попытка не нужна


if __name__ == "__main__":
    unittest.main()
