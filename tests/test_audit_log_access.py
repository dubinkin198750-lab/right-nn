"""Тесты /api/audit-log — доступ только для роли admin (раньше не было
защиты роли вообще: любой вошедший, включая viewer, мог его открыть)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage, auth  # noqa: E402


class TestAuditLogAccess(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        # require_role полностью отключается, если в системе вообще нет ни
        # одного пользователя (auth.is_enabled() смотрит storage.load_users())
        storage.create_user("admin1", auth.hash_password("x" * 10), "admin")
        self.client = app.test_client()

    def test_admin_can_view_audit_log(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "admin1"
            sess["role"] = "admin"
        resp = self.client.get("/api/audit-log")
        self.assertEqual(resp.status_code, 200)

    def test_editor_cannot_view_audit_log(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"
        resp = self.client.get("/api/audit-log")
        self.assertEqual(resp.status_code, 403)

    def test_viewer_cannot_view_audit_log(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "viewer1"
            sess["role"] = "viewer"
        resp = self.client.get("/api/audit-log")
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_cannot_view_audit_log(self):
        resp = self.client.get("/api/audit-log")
        self.assertIn(resp.status_code, (401, 403))  # 401 — не вошёл вообще; 403 — вошёл, но не та роль


if __name__ == "__main__":
    unittest.main()
