"""Тесты правила «в системе может быть только один администратор» —
и через users.json (динамические пользователи), и с учётом старого
способа входа через .env (APP_USERS), который тоже всегда даёт роль admin.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import auth, storage  # noqa: E402
from tests._helpers import IsolatedStorageTestCase  # noqa: E402


class EnvIsolatedTestCase(IsolatedStorageTestCase):
    """Как AuthTestCase в test_auth.py — изолирует APP_USERS поверх
    изоляции storage, чтобы тесты не зависели от .env текущего окружения."""

    def setUp(self):
        super().setUp()
        self._orig_env = os.environ.get("APP_USERS")
        os.environ.pop("APP_USERS", None)

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("APP_USERS", None)
        else:
            os.environ["APP_USERS"] = self._orig_env
        super().tearDown()


class TestEnvAdminCount(EnvIsolatedTestCase):
    def test_zero_when_app_users_not_set(self):
        self.assertEqual(auth.env_admin_count(), 0)

    def test_counts_each_env_user_as_admin(self):
        os.environ["APP_USERS"] = "иван:pass1,мария:pass2"
        self.assertEqual(auth.env_admin_count(), 2)

    def test_single_env_user(self):
        os.environ["APP_USERS"] = "admin:secret"
        self.assertEqual(auth.env_admin_count(), 1)


class TestSingleAdminEndpoints(EnvIsolatedTestCase):
    """Через Flask test client — те же проверки, что видит реальный
    пользователь при попытке создать второго admin."""

    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        self.admin_user = storage.create_user("admin1", auth.hash_password("x"), "admin")

    def _login_as_admin(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "admin1"
            sess["role"] = "admin"

    def test_cannot_create_invite_with_admin_role_when_one_exists(self):
        self._login_as_admin()
        resp = self.client.post("/api/invites", json={"role": "admin"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("только один", resp.get_json()["error"])

    def test_can_create_invite_with_editor_role(self):
        self._login_as_admin()
        resp = self.client.post("/api/invites", json={"role": "editor"})
        self.assertEqual(resp.status_code, 201)

    def test_cannot_promote_user_to_admin_when_one_exists(self):
        self._login_as_admin()
        editor = storage.create_user("editor1", auth.hash_password("x"), "editor")
        resp = self.client.put(f"/api/users/{editor['id']}", json={"role": "admin"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("только один", resp.get_json()["error"])

    def test_cannot_downgrade_the_only_admin(self):
        self._login_as_admin()
        resp = self.client.put(f"/api/users/{self.admin_user['id']}", json={"role": "editor"})
        self.assertEqual(resp.status_code, 400)

    def test_cannot_create_invite_with_admin_role_when_env_admin_exists(self):
        """Регрессия ровно на ту дыру, которую нашли при самокритике:
        APP_USERS даёт admin в обход users.json, и правило «только один»
        должно учитывать это тоже, а не только динамических пользователей."""
        storage.delete_user(self.admin_user["id"])  # в users.json теперь ни одного admin
        os.environ["APP_USERS"] = "legacy_admin:pass"  # но один admin есть через .env
        self._login_as_admin()  # сессия всё ещё валидна для маршрута (роль не перепроверяется по БД в этом тесте)
        resp = self.client.post("/api/invites", json={"role": "admin"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("только один", resp.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
