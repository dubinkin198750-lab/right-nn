"""Тесты на систему временных разрешений для справочника «Поиск по
сайтам» (storage.has_active_site_access_grant, /api/site-access-grants,
и что редактор без разрешения не может править сайты, а admin — всегда
может). Устроено так же, как разрешения на документы автора, но без
привязки к конкретному автору — справочник сайтов общий на всё
приложение (см. заметку разработки, 03.09)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


class TestHasActiveSiteAccessGrantLogic(IsolatedStorageTestCase):
    def test_no_grants_at_all(self):
        self.assertFalse(storage.has_active_site_access_grant("editor1"))

    def test_active_grant_grants_access(self):
        storage.create_site_access_grant(username="editor1", granted_by="admin1", expires_at=time.time() + 3600)
        self.assertTrue(storage.has_active_site_access_grant("editor1"))

    def test_grant_for_different_user_does_not_apply(self):
        storage.create_site_access_grant(username="editor1", granted_by="admin1", expires_at=time.time() + 3600)
        self.assertFalse(storage.has_active_site_access_grant("editor2"))

    def test_expired_grant_does_not_grant_access(self):
        storage.create_site_access_grant(username="editor1", granted_by="admin1", expires_at=time.time() - 10)
        self.assertFalse(storage.has_active_site_access_grant("editor1"))

    def test_revoked_grant_does_not_grant_access(self):
        grant = storage.create_site_access_grant(username="editor1", granted_by="admin1", expires_at=time.time() + 3600)
        storage.revoke_site_access_grant(grant["id"])
        self.assertFalse(storage.has_active_site_access_grant("editor1"))


class TestSiteAccessGrantsEndpoints(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        from backend import auth
        storage.create_user("admin1", auth.hash_password("x" * 10), "admin")
        storage.create_user("editor1", auth.hash_password("x" * 10), "editor")
        storage.create_user("editor2", auth.hash_password("x" * 10), "editor")
        self.client = app.test_client()

    def _login_as(self, username, role):
        with self.client.session_transaction() as sess:
            sess["username"] = username
            sess["role"] = role

    def test_admin_can_create_grant(self):
        self._login_as("admin1", "admin")
        resp = self.client.post("/api/site-access-grants", json={"username": "editor1", "duration_days": 3})
        self.assertEqual(resp.status_code, 201)
        self.assertAlmostEqual(resp.get_json()["expires_at"], time.time() + 3 * 86400, delta=5)

    def test_editor_cannot_create_grant(self):
        self._login_as("editor1", "editor")
        resp = self.client.post("/api/site-access-grants", json={"username": "editor2", "duration_days": 3})
        self.assertEqual(resp.status_code, 403)

    def _admin_site(self):
        self._login_as("admin1", "admin")
        return self.client.post("/api/sites", json={"name": "т", "url_template": "https://x.test", "type": "auto"}).get_json()["id"]

    def test_editor_without_grant_can_add_site(self):
        """С 23.09 добавлять сайты может любой редактор — изменение и
        удаление по-прежнему требуют разрешения."""
        self._login_as("editor1", "editor")
        resp = self.client.post("/api/sites", json={"name": "т", "url_template": "https://x.test", "type": "auto"})
        self.assertEqual(resp.status_code, 201)

    def test_editor_without_grant_cannot_update_site(self):
        site_id = self._admin_site()
        self._login_as("editor1", "editor")
        resp = self.client.put(f"/api/sites/{site_id}", json={"name": "т2"})
        self.assertEqual(resp.status_code, 403)

    def test_duplicate_base_domain_rejected(self):
        self._login_as("editor1", "editor")
        self.client.post("/api/sites", json={"name": "a", "url_template": "https://s66.zapret.me", "type": "auto"})
        resp = self.client.post("/api/sites", json={"name": "b", "url_template": "s67.zapret.me", "type": "auto"})
        self.assertEqual(resp.status_code, 409)

    def test_editor_with_active_grant_can_create_site(self):
        self._login_as("admin1", "admin")
        self.client.post("/api/site-access-grants", json={"username": "editor1", "duration_days": 3})
        self._login_as("editor1", "editor")
        resp = self.client.post("/api/sites", json={"name": "т", "url_template": "https://x.test", "type": "auto"})
        self.assertEqual(resp.status_code, 201)

    def test_editor_with_grant_for_different_user_still_cannot(self):
        site_id = self._admin_site()
        self.client.post("/api/site-access-grants", json={"username": "editor2", "duration_days": 3})
        self._login_as("editor1", "editor")
        resp = self.client.put(f"/api/sites/{site_id}", json={"name": "т2"})
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_always_create_site_without_any_grant(self):
        self._login_as("admin1", "admin")
        resp = self.client.post("/api/sites", json={"name": "т", "url_template": "https://x.test", "type": "auto"})
        self.assertEqual(resp.status_code, 201)

    def test_grant_covers_update_and_delete_too(self):
        self._login_as("admin1", "admin")
        self.client.post("/api/site-access-grants", json={"username": "editor1", "duration_days": 3})
        create_resp = self.client.post("/api/sites", json={"name": "т", "url_template": "https://x.test", "type": "auto"})
        site_id = create_resp.get_json()["id"]

        self._login_as("editor1", "editor")
        update_resp = self.client.put(f"/api/sites/{site_id}", json={"name": "т2"})
        self.assertEqual(update_resp.status_code, 200)
        delete_resp = self.client.delete(f"/api/sites/{site_id}")
        self.assertEqual(delete_resp.status_code, 200)

    def test_revoked_grant_immediately_blocks_editor(self):
        self._login_as("admin1", "admin")
        site_id = self._admin_site()
        grant_resp = self.client.post("/api/site-access-grants", json={"username": "editor1", "duration_days": 3})
        self.client.delete(f"/api/site-access-grants/{grant_resp.get_json()['id']}")

        self._login_as("editor1", "editor")
        resp = self.client.put(f"/api/sites/{site_id}", json={"name": "т2"})
        self.assertEqual(resp.status_code, 403)

    def test_mine_endpoint_reflects_current_access(self):
        self._login_as("editor1", "editor")
        resp = self.client.get("/api/site-access-grants/mine")
        self.assertFalse(resp.get_json()["has_access"])

        self._login_as("admin1", "admin")
        self.client.post("/api/site-access-grants", json={"username": "editor1", "duration_days": 3})

        self._login_as("editor1", "editor")
        resp = self.client.get("/api/site-access-grants/mine")
        self.assertTrue(resp.get_json()["has_access"])

    def test_anyone_logged_in_can_still_view_sites_list(self):
        """Право РЕДАКТИРОВАТЬ — по разрешению, а вот сам список сайтов
        читать может любой залогиненный, как и раньше (это не секретные
        данные)."""
        self._login_as("editor1", "editor")
        resp = self.client.get("/api/sites")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
