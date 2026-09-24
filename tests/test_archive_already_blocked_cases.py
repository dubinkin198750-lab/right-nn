"""Тесты backend/archive_already_blocked_cases.py — разовый скрипт для
переноса в архив дел, ставших «заблокировано» до появления автоматической
архивации (см. заметку разработки от 01.09/02.09)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage, archive_already_blocked_cases as script  # noqa: E402


class TestArchiveAlreadyBlockedCases(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        self.author = storage.upsert_author({"id": None, "name": "Автор"})

    def _case(self, **overrides):
        base = {"title": "т", "url": "https://x.test/1", "author_name": self.author["name"]}
        base.update(overrides)
        return storage.add_blocking_case(base)

    def test_report_does_not_modify_anything(self):
        case = self._case()
        storage.update_blocking_case(case["id"], {"claim_decision": "заблокировано"})
        script.report()  # не должно бросать исключений и не должно ничего менять
        self.assertIsNotNone(storage.get_blocking_case(case["id"]))
        self.assertEqual(storage.load_report_archive(), [])

    def test_apply_archives_blocked_case_without_needs_resend(self):
        case = self._case()
        storage.update_blocking_case(case["id"], {"claim_decision": "заблокировано"})
        script.apply_fix()
        self.assertIsNone(storage.get_blocking_case(case["id"]))
        archived = storage.get_report_archive_for_author(self.author["name"])
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0]["id"], case["id"])

    def test_apply_fills_missing_block_date_with_today(self):
        case = self._case()
        storage.update_blocking_case(case["id"], {"claim_decision": "заблокировано", "block_date": ""})
        script.apply_fix()
        archived = storage.get_report_archive_for_author(self.author["name"])
        self.assertEqual(archived[0]["block_date"], time.strftime("%Y-%m-%d"))

    def test_apply_does_not_overwrite_existing_block_date(self):
        case = self._case()
        storage.update_blocking_case(case["id"], {"claim_decision": "заблокировано", "block_date": "2026-01-15"})
        script.apply_fix()
        archived = storage.get_report_archive_for_author(self.author["name"])
        self.assertEqual(archived[0]["block_date"], "2026-01-15")

    def test_case_with_needs_resend_is_not_archived(self):
        case = self._case()
        storage.update_blocking_case(case["id"], {"claim_decision": "заблокировано", "needs_resend": True})
        script.apply_fix()
        self.assertIsNotNone(storage.get_blocking_case(case["id"]))
        self.assertEqual(storage.load_report_archive(), [])

    def test_case_not_blocked_is_left_alone(self):
        case = self._case()
        storage.update_blocking_case(case["id"], {"claim_decision": "отклонено"})
        script.apply_fix()
        self.assertIsNotNone(storage.get_blocking_case(case["id"]))
        self.assertEqual(storage.load_report_archive(), [])

    def test_any_of_three_decision_fields_triggers_archiving(self):
        for field in ("claim_decision", "first_appeal_decision", "repeat_appeal_decision"):
            case = self._case(url=f"https://x.test/{field}")
            storage.update_blocking_case(case["id"], {field: "заблокировано"})
        script.apply_fix()
        self.assertEqual(len(storage.load_blocking_cases()), 0)
        self.assertEqual(len(storage.get_report_archive_for_author(self.author["name"])), 3)

    def test_custom_report_period_start_day_respected(self):
        author2 = storage.upsert_author({"id": None, "name": "Автор2", "report_period_start_day": 28})
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/2", "author_name": author2["name"]})
        storage.update_blocking_case(case["id"], {"claim_decision": "заблокировано"})
        script.apply_fix()
        archived = storage.get_report_archive_for_author(author2["name"])
        self.assertEqual(len(archived), 1)  # само по себе — что перенесено; точный расчёт периода уже покрыт test_report_period.py


if __name__ == "__main__":
    unittest.main()
