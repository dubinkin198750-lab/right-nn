"""Тесты на систему временных разрешений (storage.has_active_document_grant
и эндпоинты /api/document-access-grants) — сотрудник без роли admin может
временно получить доступ на ПРОСМОТР документов/личных данных конкретного
автора или всех авторов сразу, на ограниченный срок.

Это чувствительные персональные данные (паспорт, СНИЛС) — тесты
сознательно многословны и проверяют не только «пускает», но и «не
пускает» в соседних случаях (другой автор, истёкший срок, отозванное
разрешение, роль editor без разрешения вообще)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


class TestHasActiveDocumentGrantLogic(IsolatedStorageTestCase):
    """Юнит-тесты чистой функции storage.has_active_document_grant,
    без HTTP — быстрее и проще для покрытия граничных случаев."""

    def test_no_grants_at_all(self):
        self.assertFalse(storage.has_active_document_grant("editor1", "author-1"))

    def test_scope_author_matches_only_that_author(self):
        storage.create_document_access_grant(
            username="editor1", scope="author", author_id="author-1",
            granted_by="admin1", expires_at=time.time() + 3600,
        )
        self.assertTrue(storage.has_active_document_grant("editor1", "author-1"))
        self.assertFalse(storage.has_active_document_grant("editor1", "author-2"))
        self.assertFalse(storage.has_active_document_grant("editor2", "author-1"))

    def test_scope_all_matches_any_author(self):
        storage.create_document_access_grant(
            username="editor1", scope="all", author_id=None,
            granted_by="admin1", expires_at=time.time() + 3600,
        )
        self.assertTrue(storage.has_active_document_grant("editor1", "author-1"))
        self.assertTrue(storage.has_active_document_grant("editor1", "author-999-anything"))

    def test_expired_grant_does_not_grant_access(self):
        storage.create_document_access_grant(
            username="editor1", scope="author", author_id="author-1",
            granted_by="admin1", expires_at=time.time() - 10,  # уже в прошлом
        )
        self.assertFalse(storage.has_active_document_grant("editor1", "author-1"))

    def test_revoked_grant_does_not_grant_access(self):
        grant = storage.create_document_access_grant(
            username="editor1", scope="author", author_id="author-1",
            granted_by="admin1", expires_at=time.time() + 3600,
        )
        storage.revoke_document_access_grant(grant["id"])
        self.assertFalse(storage.has_active_document_grant("editor1", "author-1"))

    def test_list_active_grants_for_username_excludes_expired_and_revoked(self):
        storage.create_document_access_grant(
            username="editor1", scope="all", author_id=None,
            granted_by="admin1", expires_at=time.time() + 3600,
        )
        expired = storage.create_document_access_grant(
            username="editor1", scope="author", author_id="author-2",
            granted_by="admin1", expires_at=time.time() + 3600,
        )
        storage.revoke_document_access_grant(expired["id"])
        active = storage.list_active_grants_for_username("editor1")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["scope"], "all")


class TestDocumentAccessGrantsEndpoints(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        from backend import auth
        storage.create_user("admin1", auth.hash_password("x" * 10), "admin")
        storage.create_user("editor1", auth.hash_password("x" * 10), "editor")
        self.client = app.test_client()
        self.author = storage.upsert_author({"id": None, "name": "Автор Тестовый"})

    def _login_as(self, username, role):
        with self.client.session_transaction() as sess:
            sess["username"] = username
            sess["role"] = role

    def test_admin_can_create_grant_with_duration_days(self):
        self._login_as("admin1", "admin")
        resp = self.client.post("/api/document-access-grants", json={
            "username": "editor1", "scope": "author", "author_id": self.author["id"],
            "duration_days": 3,
        })
        self.assertEqual(resp.status_code, 201)
        grant = resp.get_json()
        self.assertEqual(grant["scope"], "author")
        self.assertAlmostEqual(grant["expires_at"], time.time() + 3 * 86400, delta=5)

    def test_editor_cannot_create_grant(self):
        self._login_as("editor1", "editor")
        resp = self.client.post("/api/document-access-grants", json={
            "username": "editor1", "scope": "all", "duration_days": 1,
        })
        self.assertEqual(resp.status_code, 403)

    def test_create_grant_rejects_unknown_username(self):
        self._login_as("admin1", "admin")
        resp = self.client.post("/api/document-access-grants", json={
            "username": "no-such-user", "scope": "all", "duration_days": 1,
        })
        self.assertEqual(resp.status_code, 400)

    def test_create_grant_requires_duration_or_expiry(self):
        self._login_as("admin1", "admin")
        resp = self.client.post("/api/document-access-grants", json={
            "username": "editor1", "scope": "all",
        })
        self.assertEqual(resp.status_code, 400)

    def test_admin_can_revoke_grant(self):
        self._login_as("admin1", "admin")
        created = self.client.post("/api/document-access-grants", json={
            "username": "editor1", "scope": "all", "duration_days": 1,
        }).get_json()
        resp = self.client.delete(f"/api/document-access-grants/{created['id']}")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(storage.has_active_document_grant("editor1", self.author["id"]))

    def test_mine_endpoint_returns_only_own_grants(self):
        self._login_as("admin1", "admin")
        self.client.post("/api/document-access-grants", json={
            "username": "editor1", "scope": "all", "duration_days": 1,
        })
        self._login_as("editor1", "editor")
        resp = self.client.get("/api/document-access-grants/mine")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.get_json()), 1)


class TestGrantUnlocksAuthorEndpoints(IsolatedStorageTestCase):
    """Сквозная проверка: editor без разрешения не видит документы/личные
    данные автора; после выдачи разрешения — видит (но не может изменить
    личные данные — PUT остаётся только у admin); после отзыва — снова
    не видит."""

    def setUp(self):
        super().setUp()
        from backend.app import app
        from backend import auth
        storage.create_user("admin1", auth.hash_password("x" * 10), "admin")
        storage.create_user("editor1", auth.hash_password("x" * 10), "editor")
        self.client = app.test_client()
        self.author = storage.upsert_author({"id": None, "name": "Автор Тестовый"})

    def _login_as(self, username, role):
        with self.client.session_transaction() as sess:
            sess["username"] = username
            sess["role"] = role

    def test_editor_without_grant_cannot_view_personal_data(self):
        self._login_as("editor1", "editor")
        resp = self.client.get(f"/api/authors/{self.author['id']}/personal-data")
        self.assertEqual(resp.status_code, 403)

    def test_editor_without_grant_cannot_list_documents(self):
        self._login_as("editor1", "editor")
        resp = self.client.get(f"/api/authors/{self.author['id']}/documents")
        self.assertEqual(resp.status_code, 403)

    def test_editor_with_grant_can_view_personal_data(self):
        self._login_as("admin1", "admin")
        self.client.post("/api/document-access-grants", json={
            "username": "editor1", "scope": "author", "author_id": self.author["id"], "duration_days": 1,
        })
        self._login_as("editor1", "editor")
        resp = self.client.get(f"/api/authors/{self.author['id']}/personal-data")
        self.assertEqual(resp.status_code, 200)

    def test_editor_with_grant_cannot_edit_personal_data(self):
        # Просмотр — да, редактирование — по-прежнему только admin.
        self._login_as("admin1", "admin")
        self.client.post("/api/document-access-grants", json={
            "username": "editor1", "scope": "author", "author_id": self.author["id"], "duration_days": 1,
        })
        self._login_as("editor1", "editor")
        resp = self.client.put(f"/api/authors/{self.author['id']}/personal-data", json={"full_name": "X"})
        self.assertEqual(resp.status_code, 403)

    def test_grant_for_other_author_does_not_unlock_this_one(self):
        other_author = storage.upsert_author({"id": None, "name": "Другой автор"})
        self._login_as("admin1", "admin")
        self.client.post("/api/document-access-grants", json={
            "username": "editor1", "scope": "author", "author_id": other_author["id"], "duration_days": 1,
        })
        self._login_as("editor1", "editor")
        resp = self.client.get(f"/api/authors/{self.author['id']}/personal-data")
        self.assertEqual(resp.status_code, 403)

    def test_revoked_grant_locks_access_again(self):
        self._login_as("admin1", "admin")
        created = self.client.post("/api/document-access-grants", json={
            "username": "editor1", "scope": "author", "author_id": self.author["id"], "duration_days": 1,
        }).get_json()
        self.client.delete(f"/api/document-access-grants/{created['id']}")
        self._login_as("editor1", "editor")
        resp = self.client.get(f"/api/authors/{self.author['id']}/personal-data")
        self.assertEqual(resp.status_code, 403)

    def test_download_endpoint_stays_admin_only_even_with_grant(self):
        # /download (скачивание исходного файла) — не то же самое, что
        # /view (просмотр). Разрешение открывает только просмотр.
        self._login_as("admin1", "admin")
        self.client.post("/api/document-access-grants", json={
            "username": "editor1", "scope": "author", "author_id": self.author["id"], "duration_days": 1,
        })
        self._login_as("editor1", "editor")
        resp = self.client.get(f"/api/authors/{self.author['id']}/documents/doesnt-matter/download")
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
