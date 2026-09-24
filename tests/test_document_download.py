"""Тесты /api/authors/<id>/documents/<doc_id>/download — в первую очередь
Content-Disposition с кириллическим именем файла, тот же класс бага, что
и в court-petition (см. test_court_petition_endpoint.py)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage, document_vault  # noqa: E402


class TestDownloadAuthorDocument(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "admin1"
            sess["role"] = "admin"
        self.author = storage.upsert_author({"id": None, "name": "Автор"})

    def _upload_doc(self, original_name):
        stored_filename = f"stored_{original_name}"
        document_vault.save_encrypted(stored_filename, b"fake pdf content")
        return storage.add_document({
            "author_id": self.author["id"], "original_name": original_name,
            "stored_filename": stored_filename, "doc_type": "доверенность",
            "description": "", "size": 10, "uploaded_at": 0,
        })

    def test_download_cyrillic_filename_returns_content(self):
        doc = self._upload_doc("Доверенность (Иванова).pdf")
        resp = self.client.get(f"/api/authors/{self.author['id']}/documents/{doc['id']}/download")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, b"fake pdf content")

    def test_content_disposition_header_survives_real_http_encoding(self):
        """Та же регрессия, что и в заявлении — Content-Disposition с
        кириллическим именем документа должен реально кодироваться в
        latin-1, иначе настоящий сервер упадёт (test_client() этого не
        покажет, см. подробное объяснение в test_court_petition_endpoint.py)."""
        doc = self._upload_doc("Договор авторского заказа Гофман.pdf")
        resp = self.client.get(f"/api/authors/{self.author['id']}/documents/{doc['id']}/download")
        self.assertEqual(resp.status_code, 200)
        header_value = resp.headers.get("Content-Disposition")
        self.assertIsNotNone(header_value)
        try:
            header_value.encode("latin-1")
        except UnicodeEncodeError:
            self.fail(f"Content-Disposition не кодируется в latin-1: {header_value!r}")

    def test_missing_document_returns_404(self):
        resp = self.client.get(f"/api/authors/{self.author['id']}/documents/no-such-id/download")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
