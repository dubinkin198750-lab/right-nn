"""Тесты архивации дел после помесячного отчёта и восстановления обратно."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import storage  # noqa: E402
from tests._helpers import IsolatedStorageTestCase  # noqa: E402


def _blocked_case(url, author_name="Автор", block_date="2026-08-05"):
    case = storage.add_blocking_case({"title": "т", "url": url, "author_name": author_name})
    return storage.update_blocking_case(case["id"], {"status": "заблокировано", "block_date": block_date})


class TestReportArchive(IsolatedStorageTestCase):
    def test_archive_moves_case_out_of_active_table(self):
        case = _blocked_case("https://x.test/1")
        storage.archive_reported_cases([case], 2026, 8)
        self.assertIsNone(storage.get_blocking_case(case["id"]))

    def test_archive_keeps_case_data_intact(self):
        case = _blocked_case("https://x.test/2", author_name="Гофман О.С.")
        storage.archive_reported_cases([case], 2026, 8)
        archived = storage.get_report_archive_for_author("Гофман О.С.")
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0]["url"], "https://x.test/2")
        self.assertEqual(archived[0]["status"], "заблокировано")

    def test_archive_records_report_month_and_year(self):
        case = _blocked_case("https://x.test/3")
        storage.archive_reported_cases([case], 2026, 8)
        archived = storage.get_report_archive_for_author("Автор")
        self.assertEqual(archived[0]["report_year"], 2026)
        self.assertEqual(archived[0]["report_month"], 8)

    def test_archive_does_not_touch_other_authors_active_cases(self):
        case_a = _blocked_case("https://x.test/a", author_name="Автор А")
        case_b = _blocked_case("https://x.test/b", author_name="Автор Б")
        storage.archive_reported_cases([case_a], 2026, 8)
        self.assertIsNone(storage.get_blocking_case(case_a["id"]))
        self.assertIsNotNone(storage.get_blocking_case(case_b["id"]))

    def test_get_report_archive_for_author_filters_by_author(self):
        case_a = _blocked_case("https://x.test/a", author_name="Автор А")
        case_b = _blocked_case("https://x.test/b", author_name="Автор Б")
        storage.archive_reported_cases([case_a, case_b], 2026, 8)
        archive_a = storage.get_report_archive_for_author("Автор А")
        self.assertEqual(len(archive_a), 1)
        self.assertEqual(archive_a[0]["url"], "https://x.test/a")

    def test_get_report_archive_sorted_newest_first(self):
        case1 = _blocked_case("https://x.test/1")
        storage.archive_reported_cases([case1], 2026, 6)
        case2 = _blocked_case("https://x.test/2")
        storage.archive_reported_cases([case2], 2026, 8)
        archived = storage.get_report_archive_for_author("Автор")
        self.assertEqual(archived[0]["url"], "https://x.test/2")  # архивировано позже — идёт первым

    def test_restore_returns_case_to_active_table(self):
        case = _blocked_case("https://x.test/restore")
        storage.archive_reported_cases([case], 2026, 8)
        restored = storage.restore_archived_case(case["id"])
        self.assertIsNotNone(restored)
        self.assertEqual(restored["url"], "https://x.test/restore")
        self.assertIsNotNone(storage.get_blocking_case(case["id"]))

    def test_restore_removes_case_from_archive(self):
        case = _blocked_case("https://x.test/restore2")
        storage.archive_reported_cases([case], 2026, 8)
        storage.restore_archived_case(case["id"])
        self.assertEqual(storage.get_report_archive_for_author("Автор"), [])

    def test_restore_strips_archive_only_fields(self):
        case = _blocked_case("https://x.test/restore3")
        storage.archive_reported_cases([case], 2026, 8)
        restored = storage.restore_archived_case(case["id"])
        self.assertNotIn("archived_at", restored)
        self.assertNotIn("report_year", restored)
        self.assertNotIn("report_month", restored)

    def test_restore_missing_case_returns_none(self):
        self.assertIsNone(storage.restore_archived_case("no-such-id"))

    def test_screenshots_are_not_deleted_on_archive(self):
        """Отличие от delete_blocking_case: скриншоты — доказательная база,
        архивация дела не должна их стирать."""
        case = _blocked_case("https://x.test/withshot")
        storage.add_screenshot({
            "case_id": case["id"], "original_name": "s.png", "stored_filename": "s.png",
            "description": "", "size": 10, "uploaded_at": 0,
        })
        storage.archive_reported_cases([case], 2026, 8)
        self.assertEqual(len(storage.get_case_screenshots(case["id"])), 1)


class TestListAllReportArchiveEndpoint(IsolatedStorageTestCase):
    """/api/report-archive — весь архив сразу, для обзорного раздела
    «Архив» в левом меню (см. заметку разработки, 02.09)."""

    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def test_returns_entries_from_all_authors_combined(self):
        case_a = _blocked_case("https://x.test/all-a", author_name="Автор А")
        case_b = _blocked_case("https://x.test/all-b", author_name="Автор Б")
        storage.archive_reported_cases([case_a], 2026, 8)
        storage.archive_reported_cases([case_b], 2026, 9)

        resp = self.client.get("/api/report-archive")
        self.assertEqual(resp.status_code, 200)
        urls = {e["url"] for e in resp.get_json()}
        self.assertEqual(urls, {"https://x.test/all-a", "https://x.test/all-b"})

    def test_empty_archive_returns_empty_list(self):
        resp = self.client.get("/api/report-archive")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), [])


if __name__ == "__main__":
    unittest.main()
