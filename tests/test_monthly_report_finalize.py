"""Тест /api/blocking-cases/monthly-report/finalize — конкретно то, что
дела, у которых needs_resend встал (заблокировано, но ссылка снова
доступна), остаются в отчёте (не пропадают), но НЕ уходят в архив вместе
с по-настоящему закрытыми делами — регрессия на пункт самокритики про
исчезающие из отчёта дела. Раньше это различалось отдельным статусом
«повторная блокировка», сейчас — комбинацией is_blocked() + needs_resend."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


class TestFinalizeMonthlyReport(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def test_blocked_case_is_archived(self):
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        storage.update_blocking_case(case["id"], {"first_appeal_decision": "заблокировано", "block_date": "2026-08-05"})

        resp = self.client.post("/api/blocking-cases/monthly-report/finalize", json={"month": "2026-08"})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(storage.get_blocking_case(case["id"]))

    def test_needs_resend_case_stays_active_not_archived(self):
        """Ключевое исправление: дело заблокировали в августе, потом
        (например, фоновой проверкой) needs_resend сам встал True — при
        завершении отчёта за август это дело ДОЛЖНО остаться в активной
        таблице, ему ещё нужно повторное заявление."""
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/2", "author_name": "А"})
        storage.update_blocking_case(case["id"], {
            "first_appeal_decision": "заблокировано", "block_date": "2026-08-05", "needs_resend": True,
        })

        resp = self.client.post("/api/blocking-cases/monthly-report/finalize", json={"month": "2026-08"})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(storage.get_blocking_case(case["id"]))

    def test_needs_resend_case_still_appears_in_the_report_file(self):
        """Дело не должно молча выпасть из самого файла отчёта — только
        не архивироваться."""
        import io
        import openpyxl

        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/3", "author_name": "А"})
        storage.update_blocking_case(case["id"], {
            "first_appeal_decision": "заблокировано", "block_date": "2026-08-05", "needs_resend": True,
        })

        resp = self.client.post("/api/blocking-cases/monthly-report/finalize", json={"month": "2026-08"})
        wb = openpyxl.load_workbook(io.BytesIO(resp.data))
        ws = wb.active
        found = any(
            cell == "https://x.test/3"
            for row in ws.iter_rows(values_only=True) for cell in row
        )
        self.assertTrue(found)

    def test_mixed_batch_archives_only_the_closed_ones(self):
        blocked = storage.add_blocking_case({"title": "т1", "url": "https://x.test/blocked", "author_name": "А"})
        storage.update_blocking_case(blocked["id"], {"first_appeal_decision": "заблокировано", "block_date": "2026-08-05"})
        repeat = storage.add_blocking_case({"title": "т2", "url": "https://x.test/repeat", "author_name": "А"})
        storage.update_blocking_case(repeat["id"], {
            "first_appeal_decision": "заблокировано", "block_date": "2026-08-06", "needs_resend": True,
        })

        self.client.post("/api/blocking-cases/monthly-report/finalize", json={"month": "2026-08"})

        self.assertIsNone(storage.get_blocking_case(blocked["id"]))
        self.assertIsNotNone(storage.get_blocking_case(repeat["id"]))


if __name__ == "__main__":
    unittest.main()
