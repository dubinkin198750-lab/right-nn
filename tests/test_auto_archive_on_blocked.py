"""Тесты автоматического переноса заблокированных дел в архив отчётов
сразу при установлении решения «заблокировано» — без ожидания конца
месяца и ручной кнопки «Завершить месяц и заархивировать» (см. app.py,
_maybe_auto_archive_blocked_case; заметка разработки от 01.09)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


class TestAutoArchiveOnBlocked(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"
        self.author = storage.upsert_author({"id": None, "name": "Автор"})

    def _case(self, **overrides):
        base = {"title": "т", "url": "https://x.test/1", "author_name": self.author["name"]}
        base.update(overrides)
        return storage.add_blocking_case(base)

    def test_setting_claim_decision_blocked_archives_immediately(self):
        case = self._case()
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"claim_decision": "заблокировано"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("auto_archived"))

        # дела больше нет в активной таблице
        self.assertIsNone(storage.get_blocking_case(case["id"]))
        # зато оно есть в архиве отчётов этого автора
        archived = storage.get_report_archive_for_author(self.author["name"])
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0]["id"], case["id"])

    def test_block_date_auto_filled_when_missing(self):
        """Дата блокировки нужна фоновому мониторингу как якорная точка
        отсчёта (см. link_check._anchor_date) — без неё заархивированное
        дело больше никогда не проверяется на предмет «ожившей» ссылки.
        Если решение стало «заблокировано», а дату блокировки никто не
        указал — сервер сам подставляет сегодняшнюю."""
        case = self._case()
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"claim_decision": "заблокировано"})
        archived = storage.get_report_archive_for_author(self.author["name"])
        self.assertEqual(archived[0]["block_date"], time.strftime("%Y-%m-%d"))

    def test_block_date_not_overwritten_if_explicitly_provided(self):
        """Если дата блокировки передана в том же запросе явно (или уже
        стояла раньше) — автоподстановка не должна её перезаписывать
        сегодняшним числом."""
        case = self._case()
        explicit_date = "2026-01-15"
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={
            "claim_decision": "заблокировано", "block_date": explicit_date,
        })
        archived = storage.get_report_archive_for_author(self.author["name"])
        self.assertEqual(archived[0]["block_date"], explicit_date)

    def test_block_date_not_touched_when_decision_is_not_blocked(self):
        """Автоподстановка срабатывает только при «заблокировано» — на
        остальные решения (отклонено/нет реакции) дата не проставляется
        и дело не архивируется."""
        case = self._case()
        self.client.put(f"/api/blocking-cases/{case['id']}", json={"claim_decision": "отклонено"})
        updated = storage.get_blocking_case(case["id"])
        self.assertEqual(updated.get("block_date"), "")

    def test_setting_first_appeal_decision_blocked_also_archives(self):
        """Решение «заблокировано» на ЛЮБОМ из трёх этапов (не только
        претензия) должно приводить к тому же — не только claim_decision."""
        case = self._case()
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"first_appeal_decision": "заблокировано"})
        self.assertTrue(resp.get_json().get("auto_archived"))
        self.assertIsNone(storage.get_blocking_case(case["id"]))

    def test_manual_blocked_decision_clears_needs_resend_and_archives(self):
        """Сотрудник вручную выбрал «заблокировано» при поднятом флаге
        needs_resend — это подтверждение блокировки человеком. Раньше флаг
        не снимался, и дело навсегда застревало в «Блокировке» (реальная
        жалоба от 22.09, ссылка s66.zapret.me)."""
        case = self._case()
        storage.update_blocking_case(case["id"], {"needs_resend": True})
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"claim_decision": "заблокировано"})
        self.assertTrue(resp.get_json().get("auto_archived"))
        self.assertIsNone(storage.get_blocking_case(case["id"]))
        archived = [e for e in storage.load_report_archive() if e["id"] == case["id"]][0]
        self.assertFalse(archived["needs_resend"])

    def test_needs_resend_on_blocked_case_prevents_archiving_on_unrelated_edit(self):
        """Дело заблокировано, но проверка нашла ссылку снова доступной —
        правка примечаний не должна молча архивировать дело."""
        case = self._case(claim_decision="заблокировано", block_date="2026-09-01")
        storage.update_blocking_case(case["id"], {"needs_resend": True})
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"notes": "смотрю"})
        self.assertNotIn("auto_archived", resp.get_json())
        self.assertIsNotNone(storage.get_blocking_case(case["id"]))

    def test_non_blocked_decision_does_not_archive(self):
        case = self._case()
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"claim_decision": "нет реакции"})
        self.assertNotIn("auto_archived", resp.get_json())
        self.assertIsNotNone(storage.get_blocking_case(case["id"]))

    def test_unrelated_field_update_does_not_trigger_archiving(self):
        """Обычное редактирование поля (например, заметки) не должно
        внезапно архивировать дело, если оно ещё не заблокировано."""
        case = self._case()
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"notes": "проверка"})
        self.assertNotIn("auto_archived", resp.get_json())
        self.assertIsNotNone(storage.get_blocking_case(case["id"]))

    def test_default_start_day_uses_plain_calendar_month(self):
        case = self._case()
        self.client.put(f"/api/blocking-cases/{case['id']}", json={"claim_decision": "заблокировано"})
        archived = storage.get_report_archive_for_author(self.author["name"])
        now = time.localtime()
        self.assertEqual(archived[0]["report_year"], now.tm_year)
        self.assertEqual(archived[0]["report_month"], now.tm_mon)

    def test_custom_start_day_affects_report_period(self):
        """Автор со своим днём начала периода (например, 28-е число) — если
        сегодня раньше этого дня в месяце, период должен считаться от
        прошлого месяца, а не текущего календарного."""
        author2 = storage.upsert_author({"id": None, "name": "Автор2", "report_period_start_day": 28})
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/2", "author_name": author2["name"]})

        now = time.localtime()
        self.client.put(f"/api/blocking-cases/{case['id']}", json={"claim_decision": "заблокировано"})
        archived = storage.get_report_archive_for_author(author2["name"])
        self.assertEqual(len(archived), 1)
        if now.tm_mday >= 28:
            self.assertEqual(archived[0]["report_year"], now.tm_year)
            self.assertEqual(archived[0]["report_month"], now.tm_mon)
        else:
            expected_month = now.tm_mon - 1 if now.tm_mon > 1 else 12
            expected_year = now.tm_year if now.tm_mon > 1 else now.tm_year - 1
            self.assertEqual(archived[0]["report_year"], expected_year)
            self.assertEqual(archived[0]["report_month"], expected_month)

    def test_restore_from_archive_brings_case_back(self):
        """Уже существующая кнопка «Восстановить из архива» должна
        по-прежнему работать для дел, заархивированных автоматически —
        не только для тех, что попали в архив через ручную кнопку
        «Завершить месяц»."""
        case = self._case()
        self.client.put(f"/api/blocking-cases/{case['id']}", json={"claim_decision": "заблокировано"})
        self.assertIsNone(storage.get_blocking_case(case["id"]))

        resp = self.client.post(f"/api/report-archive/{case['id']}/restore")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(storage.get_blocking_case(case["id"]))
        self.assertEqual(len(storage.get_report_archive_for_author(self.author["name"])), 0)


if __name__ == "__main__":
    unittest.main()
