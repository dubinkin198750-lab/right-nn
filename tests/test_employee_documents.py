"""Тесты /api/me/documents — личные документы сотрудника (доверенность
от фирмы и т.п.), автоматически прикладываемые к каждому заявлению,
которое он готовит."""
import io
import os
import sys
import time
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage, author_personal_data  # noqa: E402


class TestMyDocumentsEndpoints(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        from backend import auth
        # require_role полностью отключается, если в системе вообще нет ни
        # одного пользователя (auth.is_enabled() смотрит storage.load_users()) —
        # без этого создания пользователя все проверки роли ниже молча не
        # сработали бы, тест на "viewer не может" прошёл бы "случайно"
        storage.create_user("editor1", auth.hash_password("x" * 10), "editor")
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def test_requires_login(self):
        from backend.app import app
        anon_client = app.test_client()
        resp = anon_client.get("/api/me/documents")
        self.assertEqual(resp.status_code, 401)

    def test_upload_and_list(self):
        resp = self.client.post(
            "/api/me/documents",
            data={"file": (io.BytesIO(b"fake pdf"), "doverennost.pdf"), "description": "доверенность от фирмы"},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 201)
        docs = self.client.get("/api/me/documents").get_json()
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["username"], "editor1")

    def test_rejects_disallowed_extension(self):
        resp = self.client.post(
            "/api/me/documents",
            data={"file": (io.BytesIO(b"x"), "script.exe")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)

    def test_users_cannot_see_each_others_documents(self):
        self.client.post(
            "/api/me/documents",
            data={"file": (io.BytesIO(b"fake"), "my.pdf")},
            content_type="multipart/form-data",
        )
        with self.client.session_transaction() as sess:
            sess["username"] = "editor2"
        docs = self.client.get("/api/me/documents").get_json()
        self.assertEqual(docs, [])

    def test_cannot_download_another_users_document(self):
        upload_resp = self.client.post(
            "/api/me/documents",
            data={"file": (io.BytesIO(b"fake"), "my.pdf")},
            content_type="multipart/form-data",
        )
        doc_id = upload_resp.get_json()["id"]
        with self.client.session_transaction() as sess:
            sess["username"] = "editor2"
        resp = self.client.get(f"/api/me/documents/{doc_id}/download")
        self.assertEqual(resp.status_code, 404)

    def test_download_returns_original_content(self):
        upload_resp = self.client.post(
            "/api/me/documents",
            data={"file": (io.BytesIO(b"real pdf content here"), "my.pdf")},
            content_type="multipart/form-data",
        )
        doc_id = upload_resp.get_json()["id"]
        resp = self.client.get(f"/api/me/documents/{doc_id}/download")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, b"real pdf content here")

    def test_delete_removes_document(self):
        upload_resp = self.client.post(
            "/api/me/documents",
            data={"file": (io.BytesIO(b"fake"), "my.pdf")},
            content_type="multipart/form-data",
        )
        doc_id = upload_resp.get_json()["id"]
        del_resp = self.client.delete(f"/api/me/documents/{doc_id}")
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(self.client.get("/api/me/documents").get_json(), [])

    def test_viewer_role_cannot_upload(self):
        """Регрессия на найденную несостыковку: по правилам приложения
        роль «только просмотр» ничего не может изменять — загрузка
        документа (даже своего) это изменение, должна быть запрещена."""
        with self.client.session_transaction() as sess:
            sess["role"] = "viewer"
        resp = self.client.post(
            "/api/me/documents",
            data={"file": (io.BytesIO(b"fake"), "my.pdf")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 403)

    def test_viewer_role_cannot_delete(self):
        upload_resp = self.client.post(
            "/api/me/documents",
            data={"file": (io.BytesIO(b"fake"), "my.pdf")},
            content_type="multipart/form-data",
        )
        doc_id = upload_resp.get_json()["id"]
        with self.client.session_transaction() as sess:
            sess["role"] = "viewer"
        resp = self.client.delete(f"/api/me/documents/{doc_id}")
        self.assertEqual(resp.status_code, 403)

    def test_viewer_role_can_still_view_and_download_own_documents(self):
        """Viewer «видит всё, ничего не может изменить» — просмотр и
        скачивание своих же документов остаётся доступен, запрещена
        только загрузка/удаление."""
        upload_resp = self.client.post(
            "/api/me/documents",
            data={"file": (io.BytesIO(b"real content"), "my.pdf")},
            content_type="multipart/form-data",
        )
        doc_id = upload_resp.get_json()["id"]
        with self.client.session_transaction() as sess:
            sess["role"] = "viewer"
        list_resp = self.client.get("/api/me/documents")
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(len(list_resp.get_json()), 1)
        download_resp = self.client.get(f"/api/me/documents/{doc_id}/download")
        self.assertEqual(download_resp.status_code, 200)
        self.assertEqual(download_resp.data, b"real content")


class TestEmployeeDocumentsAttachedToPetition(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"
        self.author = storage.upsert_author({"id": None, "name": "Автор"})
        author_personal_data.save(self.author["id"], {"full_name": "Автор"})

    def _prepare_and_download(self, case_ids, timeout=10):
        """См. тот же хелпер в test_court_petition_endpoint.py — подготовка
        теперь асинхронная (job_id + опрос + скачивание), эмулируем это же
        поведение здесь, чтобы не переписывать сами проверки ниже."""
        start_resp = self.client.post(f"/api/authors/{self.author['id']}/court-petition", json={"case_ids": case_ids})
        job_id = start_resp.get_json()["job_id"]
        deadline = time.time() + timeout
        while time.time() < deadline:
            poll_resp = self.client.get(f"/api/authors/{self.author['id']}/court-petition/{job_id}")
            if poll_resp.get_json()["status"] == "done":
                break
            time.sleep(0.05)
        else:
            self.fail("Фоновая задача подготовки заявления не завершилась за отведённое время")
        return self.client.get(f"/api/authors/{self.author['id']}/court-petition/{job_id}/download")

    def test_petition_includes_submitting_employees_own_documents(self):
        self.client.post(
            "/api/me/documents",
            data={"file": (io.BytesIO(b"proxy content"), "doverennost.pdf")},
            content_type="multipart/form-data",
        )
        case = storage.add_blocking_case({
            "title": "т", "url": "https://x.test/1", "author_name": self.author["name"], "status": "в работе",
        })
        resp = self._prepare_and_download([case["id"]])
        self.assertEqual(resp.status_code, 200)
        names = zipfile.ZipFile(io.BytesIO(resp.data)).namelist()
        # Структура архива изменилась (см. заметку разработки, п.2) —
        # документы специалиста теперь в общей папке "документы автора/",
        # с префиксом "специалист — " в имени файла, не в отдельной папке.
        self.assertTrue(any(n.startswith("документы автора/специалист — ") for n in names))

    def test_petition_does_not_include_other_employees_documents(self):
        """Только документы ТЕКУЩЕГО подающего — не всех сотрудников подряд."""
        with self.client.session_transaction() as sess:
            sess["username"] = "editor2"
        self.client.post(
            "/api/me/documents",
            data={"file": (io.BytesIO(b"someone elses proxy"), "not-mine.pdf")},
            content_type="multipart/form-data",
        )
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"

        case = storage.add_blocking_case({
            "title": "т", "url": "https://x.test/1", "author_name": self.author["name"], "status": "в работе",
        })
        resp = self._prepare_and_download([case["id"]])
        names = zipfile.ZipFile(io.BytesIO(resp.data)).namelist()
        self.assertFalse(any("not-mine.pdf" in n for n in names))

    def test_petition_works_fine_with_no_employee_documents_at_all(self):
        """Раньше не было такой категории вообще — не должно ничего сломать
        для сотрудников, у которых ещё не загружено ни одного документа."""
        case = storage.add_blocking_case({
            "title": "т", "url": "https://x.test/1", "author_name": self.author["name"], "status": "в работе",
        })
        resp = self._prepare_and_download([case["id"]])
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
