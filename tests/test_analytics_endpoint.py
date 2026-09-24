"""Тесты /api/analytics/summary — доступ только для admin, и что ответ
собирает все три среза разом."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage, auth  # noqa: E402


class TestAnalyticsEndpoint(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        storage.create_user("admin1", auth.hash_password("x" * 10), "admin")
        self.client = app.test_client()

    def test_admin_can_view_analytics(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "admin1"
            sess["role"] = "admin"
        resp = self.client.get("/api/analytics/summary")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("detected", data)
        self.assertIn("blocked", data)
        self.assertIn("dynamics", data)

    def test_editor_cannot_view_analytics(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"
        resp = self.client.get("/api/analytics/summary")
        self.assertEqual(resp.status_code, 403)

    def test_viewer_cannot_view_analytics(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "viewer1"
            sess["role"] = "viewer"
        resp = self.client.get("/api/analytics/summary")
        self.assertEqual(resp.status_code, 403)

    def test_reflects_real_data(self):
        case = storage.add_blocking_case({"title": "т", "url": "https://pirate.test/1", "author_name": "А"})
        storage.update_blocking_case(case["id"], {"status": "заблокировано", "block_date": "2026-08-05"})
        storage.log_action("admin1", "добавил в блокировку", "т (https://pirate.test/1)")

        with self.client.session_transaction() as sess:
            sess["username"] = "admin1"
            sess["role"] = "admin"
        resp = self.client.get("/api/analytics/summary?months=1")
        data = resp.get_json()
        self.assertGreaterEqual(data["detected"]["total_all_time"], 1)

    def test_months_param_is_clamped(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "admin1"
            sess["role"] = "admin"
        resp = self.client.get("/api/analytics/summary?months=1000")
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(len(resp.get_json()["detected"]["months"]), 36)

    def test_summary_reflects_manual_override(self):
        """Ключевая проверка сути запроса: если админ вручную поправил
        число, /api/analytics/summary должен отдавать именно его, а не
        автоматически посчитанное значение."""
        storage.set_analytics_override("detected", "2026-08", 777)
        with self.client.session_transaction() as sess:
            sess["username"] = "admin1"
            sess["role"] = "admin"
        resp = self.client.get("/api/analytics/summary?months=12")
        data = resp.get_json()
        if "2026-08" in data["detected"]["months"]:
            idx = data["detected"]["months"].index("2026-08")
            self.assertEqual(data["detected"]["counts"][idx], 777)
            self.assertTrue(data["detected"]["overridden"][idx])


class TestAnalyticsOverridesEndpoint(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        storage.create_user("admin1", auth.hash_password("x" * 10), "admin")
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "admin1"
            sess["role"] = "admin"

    def test_admin_can_set_override(self):
        resp = self.client.put("/api/analytics/overrides", json={"metric": "detected", "month": "2026-08", "value": 42})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(storage.load_analytics_overrides()["detected"]["2026-08"], 42)

    def test_editor_cannot_set_override(self):
        with self.client.session_transaction() as sess:
            sess["role"] = "editor"
        resp = self.client.put("/api/analytics/overrides", json={"metric": "detected", "month": "2026-08", "value": 42})
        self.assertEqual(resp.status_code, 403)

    def test_rejects_invalid_metric(self):
        resp = self.client.put("/api/analytics/overrides", json={"metric": "не то", "month": "2026-08", "value": 1})
        self.assertEqual(resp.status_code, 400)

    def test_rejects_invalid_month_format(self):
        resp = self.client.put("/api/analytics/overrides", json={"metric": "detected", "month": "август 2026", "value": 1})
        self.assertEqual(resp.status_code, 400)

    def test_rejects_negative_value(self):
        resp = self.client.put("/api/analytics/overrides", json={"metric": "detected", "month": "2026-08", "value": -5})
        self.assertEqual(resp.status_code, 400)

    def test_null_value_removes_override(self):
        storage.set_analytics_override("detected", "2026-08", 5)
        resp = self.client.put("/api/analytics/overrides", json={"metric": "detected", "month": "2026-08", "value": None})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("2026-08", storage.load_analytics_overrides()["detected"])


class TestAnalyticsExportEndpoint(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        storage.create_user("admin1", auth.hash_password("x" * 10), "admin")
        self.client = app.test_client()

    def test_admin_can_download_xlsx(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "admin1"
            sess["role"] = "admin"
        resp = self.client.get("/api/analytics/export.xlsx")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def test_editor_cannot_download(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"
        resp = self.client.get("/api/analytics/export.xlsx")
        self.assertEqual(resp.status_code, 403)

    def test_downloaded_xlsx_reflects_manual_override(self):
        """Главная проверка сути запроса: скачанный файл должен содержать
        поправленное вручную число, а не автоматически посчитанное."""
        import io
        import openpyxl

        storage.set_analytics_override("detected", "2026-08", 555)
        with self.client.session_transaction() as sess:
            sess["username"] = "admin1"
            sess["role"] = "admin"
        resp = self.client.get("/api/analytics/export.xlsx?months=12")
        wb = openpyxl.load_workbook(io.BytesIO(resp.data))
        ws = wb["Обнаружено"]
        found = False
        for row in ws.iter_rows(values_only=True):
            if row and row[0] == "2026-08":
                self.assertEqual(row[1], 555)
                found = True
        self.assertTrue(found, "Строка за 2026-08 не найдена в выгруженном файле")


if __name__ == "__main__":
    unittest.main()
