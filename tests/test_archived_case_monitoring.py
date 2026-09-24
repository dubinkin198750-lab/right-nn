"""Тесты фонового мониторинга архивных дел (см. jobs.py,
_check_due_archived_cases_once) — реализация «Варианта 2» из обсуждения
01.09: авторхивация мгновенная, но мониторинг доступности ссылки
продолжается и для уже заархивированных дел, чтобы поймать «ожившую»
после блокировки ссылку."""
import os
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage, jobs  # noqa: E402


class TestArchivedCaseMonitoring(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"
        self.author = storage.upsert_author({"id": None, "name": "Автор"})

    def _archive_blocked_case(self, block_date=None):
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": self.author["name"]})
        patch_data = {"claim_decision": "заблокировано"}
        if block_date:
            patch_data["block_date"] = block_date
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json=patch_data)
        self.assertTrue(resp.get_json().get("auto_archived"))
        self.assertIsNone(storage.get_blocking_case(case["id"]))
        return case["id"]

    def test_revived_archived_link_gets_restored_to_active_table(self):
        past = time.strftime("%Y-%m-%d", time.localtime(time.time() - 20 * 86400))
        case_id = self._archive_blocked_case(block_date=past)

        with patch("backend.link_check.check", return_value=("доступна", time.time())):
            jobs._check_due_cases_once()

        restored = storage.get_blocking_case(case_id)
        self.assertIsNotNone(restored, "дело не вернулось в активную «Блокировку» после того, как ссылка снова стала доступна")
        self.assertTrue(restored["needs_resend"])
        self.assertEqual(len(storage.get_report_archive_for_author(self.author["name"])), 0)

    def test_still_unavailable_link_stays_archived_but_checked_timestamp_updates(self):
        past = time.strftime("%Y-%m-%d", time.localtime(time.time() - 20 * 86400))
        case_id = self._archive_blocked_case(block_date=past)

        with patch("backend.link_check.check", return_value=("недоступна", time.time())):
            jobs._check_due_cases_once()

        self.assertIsNone(storage.get_blocking_case(case_id))  # всё ещё в архиве, не восстановлено
        archived = storage.get_report_archive_for_author(self.author["name"])
        self.assertEqual(len(archived), 1)
        self.assertTrue(archived[0].get("link_checked_at"))  # но факт проверки зафиксирован

    def test_archived_case_without_block_date_is_never_checked(self):
        """Существующее (не новое) поведение: без якорной даты (block_date)
        мониторинг вообще не запускается — ни для активных дел, ни теперь
        для архивных. Проверяем, что расширение мониторинга на архив не
        сломало это правило."""
        self._archive_blocked_case(block_date=None)
        with patch("backend.link_check.check") as mock_check:
            jobs._check_due_cases_once()
        mock_check.assert_not_called()

    def test_recently_blocked_case_not_checked_before_grace_period(self):
        """block_date = сегодня — 14-дневный срок ещё не прошёл, проверка
        пока не должна запускаться (ни разу)."""
        today = time.strftime("%Y-%m-%d")
        self._archive_blocked_case(block_date=today)
        with patch("backend.link_check.check") as mock_check:
            jobs._check_due_cases_once()
        mock_check.assert_not_called()

    def test_active_cases_still_checked_alongside_archived_ones(self):
        """Расширение на архив не должно случайно отключить проверку
        обычных активных дел — оба цикла должны отработать за один вызов."""
        past = time.strftime("%Y-%m-%d", time.localtime(time.time() - 20 * 86400))
        active_case = storage.add_blocking_case({
            "title": "т", "url": "https://active.test/1", "author_name": self.author["name"],
            "petition_filed_at": past,
        })
        archived_case_id = self._archive_blocked_case(block_date=past)

        with patch("backend.link_check.check", return_value=("недоступна", time.time())):
            jobs._check_due_cases_once()

        updated_active = storage.get_blocking_case(active_case["id"])
        self.assertTrue(updated_active.get("link_checked_at"))  # активное дело тоже проверилось
        self.assertIsNone(storage.get_blocking_case(archived_case_id))  # архивное осталось в архиве


if __name__ == "__main__":
    unittest.main()
