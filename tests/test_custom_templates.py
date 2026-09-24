"""Тесты на произвольные шаблоны — раздел «Шаблоны», возможность добавить
свой шаблон (не только редактировать два фиксированных — претензия
хостингу и Avito). Хранятся в settings.json (storage.custom_templates)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


class TestCustomTemplateStorage(IsolatedStorageTestCase):
    def test_empty_by_default(self):
        self.assertEqual(storage.load_custom_templates(), [])

    def test_create_and_load(self):
        t = storage.create_custom_template("VK жалоба", "Тема", "Текст жалобы {url}")
        self.assertIn("id", t)
        loaded = storage.load_custom_templates()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["name"], "VK жалоба")

    def test_update(self):
        t = storage.create_custom_template("VK жалоба", "Тема", "Текст")
        updated = storage.update_custom_template(t["id"], "VK жалоба v2", "Новая тема", "Новый текст")
        self.assertEqual(updated["name"], "VK жалоба v2")
        self.assertEqual(storage.load_custom_templates()[0]["body"], "Новый текст")

    def test_update_unknown_id_returns_none(self):
        self.assertIsNone(storage.update_custom_template("no-such-id", "x", "y", "z"))

    def test_delete(self):
        t = storage.create_custom_template("VK жалоба", "Тема", "Текст")
        self.assertTrue(storage.delete_custom_template(t["id"]))
        self.assertEqual(storage.load_custom_templates(), [])

    def test_delete_unknown_id_returns_false(self):
        self.assertFalse(storage.delete_custom_template("no-such-id"))

    def test_multiple_templates_independent(self):
        storage.create_custom_template("Шаблон А", "", "Текст А")
        storage.create_custom_template("Шаблон Б", "", "Текст Б")
        self.assertEqual(len(storage.load_custom_templates()), 2)


class TestCustomTemplateEndpoints(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        from backend import auth
        storage.create_user("editor1", auth.hash_password("x" * 10), "editor")
        storage.create_user("viewer1", auth.hash_password("x" * 10), "viewer")
        self.client = app.test_client()

    def _login_as(self, username, role):
        with self.client.session_transaction() as sess:
            sess["username"] = username
            sess["role"] = role

    def test_anyone_logged_in_can_list(self):
        self._login_as("viewer1", "viewer")
        resp = self.client.get("/api/custom-templates")
        self.assertEqual(resp.status_code, 200)

    def test_editor_can_create(self):
        self._login_as("editor1", "editor")
        resp = self.client.post("/api/custom-templates", json={
            "name": "Instagram жалоба", "subject": "", "body": "Текст {url}",
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["name"], "Instagram жалоба")

    def test_viewer_cannot_create(self):
        self._login_as("viewer1", "viewer")
        resp = self.client.post("/api/custom-templates", json={"name": "X", "body": "Y"})
        self.assertEqual(resp.status_code, 403)

    def test_create_requires_name(self):
        self._login_as("editor1", "editor")
        resp = self.client.post("/api/custom-templates", json={"name": "", "body": "Текст"})
        self.assertEqual(resp.status_code, 400)

    def test_create_requires_body(self):
        self._login_as("editor1", "editor")
        resp = self.client.post("/api/custom-templates", json={"name": "X", "body": ""})
        self.assertEqual(resp.status_code, 400)

    def test_editor_can_update_and_delete(self):
        self._login_as("editor1", "editor")
        created = self.client.post("/api/custom-templates", json={"name": "X", "body": "Y"}).get_json()
        upd = self.client.put(f"/api/custom-templates/{created['id']}", json={"name": "X2", "body": "Y2"})
        self.assertEqual(upd.status_code, 200)
        self.assertEqual(upd.get_json()["name"], "X2")
        deleted = self.client.delete(f"/api/custom-templates/{created['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/custom-templates").get_json(), [])

    def test_update_unknown_returns_404(self):
        self._login_as("editor1", "editor")
        resp = self.client.put("/api/custom-templates/no-such-id", json={"name": "X", "body": "Y"})
        self.assertEqual(resp.status_code, 404)

    def test_delete_unknown_returns_404(self):
        self._login_as("editor1", "editor")
        resp = self.client.delete("/api/custom-templates/no-such-id")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
