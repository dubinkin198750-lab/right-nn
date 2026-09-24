"""Тесты списка записей «Другое» (backend/app.py: add_other_complaint,
remove_other_complaint) — обращений на сторонние площадки, не входящие в
готовый список (Avito/Google), может быть сколько угодно на одно дело, не
одна запись, как было в первой версии этой функции."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


class TestOtherComplaintsStorage(IsolatedStorageTestCase):
    def test_new_case_has_empty_list_by_default(self):
        c = storage.add_blocking_case({"title": "т", "url": "https://x.test/1"})
        self.assertEqual(c["other_complaints"], [])

    def test_add_entry(self):
        c = storage.add_blocking_case({"title": "т", "url": "https://x.test/1"})
        entry = {"id": "e1", "filed_at": "2026-08-15", "method": "VK", "notes": ""}
        updated = storage.add_other_complaint_entry(c["id"], entry)
        self.assertEqual(len(updated["other_complaints"]), 1)
        self.assertEqual(updated["other_complaints"][0]["method"], "VK")

    def test_add_multiple_entries_for_different_platforms(self):
        """Ключевая суть запроса — можно добавить несколько записей на
        разные площадки для одного и того же дела."""
        c = storage.add_blocking_case({"title": "т", "url": "https://x.test/1"})
        storage.add_other_complaint_entry(c["id"], {"id": "e1", "filed_at": "2026-08-01", "method": "VK", "notes": ""})
        storage.add_other_complaint_entry(c["id"], {"id": "e2", "filed_at": "2026-08-05", "method": "Meta", "notes": ""})
        updated = storage.add_other_complaint_entry(c["id"], {"id": "e3", "filed_at": "2026-08-10", "method": "торрент-трекер", "notes": ""})
        self.assertEqual(len(updated["other_complaints"]), 3)
        methods = {e["method"] for e in updated["other_complaints"]}
        self.assertEqual(methods, {"VK", "Meta", "торрент-трекер"})

    def test_delete_entry(self):
        c = storage.add_blocking_case({"title": "т", "url": "https://x.test/1"})
        storage.add_other_complaint_entry(c["id"], {"id": "e1", "filed_at": "2026-08-01", "method": "VK", "notes": ""})
        updated = storage.delete_other_complaint_entry(c["id"], "e1")
        self.assertEqual(updated["other_complaints"], [])

    def test_delete_only_removes_the_specified_entry(self):
        c = storage.add_blocking_case({"title": "т", "url": "https://x.test/1"})
        storage.add_other_complaint_entry(c["id"], {"id": "e1", "filed_at": "2026-08-01", "method": "VK", "notes": ""})
        storage.add_other_complaint_entry(c["id"], {"id": "e2", "filed_at": "2026-08-05", "method": "Meta", "notes": ""})
        updated = storage.delete_other_complaint_entry(c["id"], "e1")
        self.assertEqual(len(updated["other_complaints"]), 1)
        self.assertEqual(updated["other_complaints"][0]["id"], "e2")

    def test_delete_unknown_entry_returns_none(self):
        c = storage.add_blocking_case({"title": "т", "url": "https://x.test/1"})
        result = storage.delete_other_complaint_entry(c["id"], "не-существует")
        self.assertIsNone(result)


class TestOtherComplaintsEndpoints(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        from backend import auth
        storage.create_user("editor1", auth.hash_password("x" * 10), "editor")
        storage.create_user("admin1", auth.hash_password("x" * 10), "admin")
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def test_add_via_endpoint(self):
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        resp = self.client.post(f"/api/blocking-cases/{case['id']}/other-complaints", json={
            "filed_at": "2026-08-15", "method": "VK", "notes": "Написали администратору группы",
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertEqual(len(data["other_complaints"]), 1)
        self.assertEqual(data["other_complaints"][0]["method"], "VK")
        self.assertIn("id", data["other_complaints"][0])

    def test_add_multiple_via_endpoint_accumulates(self):
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        self.client.post(f"/api/blocking-cases/{case['id']}/other-complaints", json={"filed_at": "2026-08-01", "method": "VK"})
        resp = self.client.post(f"/api/blocking-cases/{case['id']}/other-complaints", json={"filed_at": "2026-08-05", "method": "Meta"})
        self.assertEqual(len(resp.get_json()["other_complaints"]), 2)

    def test_add_requires_filed_at_and_method(self):
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        resp = self.client.post(f"/api/blocking-cases/{case['id']}/other-complaints", json={"filed_at": "2026-08-01"})
        self.assertEqual(resp.status_code, 400)
        resp2 = self.client.post(f"/api/blocking-cases/{case['id']}/other-complaints", json={"method": "VK"})
        self.assertEqual(resp2.status_code, 400)

    def test_add_404_for_unknown_case(self):
        resp = self.client.post("/api/blocking-cases/does-not-exist/other-complaints", json={"filed_at": "2026-08-01", "method": "VK"})
        self.assertEqual(resp.status_code, 404)

    def test_viewer_cannot_add(self):
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        with self.client.session_transaction() as sess:
            sess["role"] = "viewer"
        resp = self.client.post(f"/api/blocking-cases/{case['id']}/other-complaints", json={"filed_at": "2026-08-01", "method": "VK"})
        self.assertEqual(resp.status_code, 403)

    def test_delete_via_endpoint(self):
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        add_resp = self.client.post(f"/api/blocking-cases/{case['id']}/other-complaints", json={"filed_at": "2026-08-01", "method": "VK"})
        entry_id = add_resp.get_json()["other_complaints"][0]["id"]
        del_resp = self.client.delete(f"/api/blocking-cases/{case['id']}/other-complaints/{entry_id}")
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(del_resp.get_json()["other_complaints"], [])

    def test_delete_unknown_entry_404(self):
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        resp = self.client.delete(f"/api/blocking-cases/{case['id']}/other-complaints/не-существует")
        self.assertEqual(resp.status_code, 404)

    def test_add_logs_to_complaint_send_log(self):
        """Каждая добавленная запись — тоже событие «отправки», должна
        попасть в специализированный журнал отправок (только admin)."""
        case = storage.add_blocking_case({
            "title": "т", "url": "https://x.test/1", "author_name": "Иванов", "work_title": "Курс",
        })
        self.client.post(f"/api/blocking-cases/{case['id']}/other-complaints", json={
            "filed_at": "2026-08-15", "method": "VK", "notes": "",
        })

        with self.client.session_transaction() as sess:
            sess["username"] = "admin1"
            sess["role"] = "admin"
        log = self.client.get("/api/complaint-send-log").get_json()
        other_entries = [e for e in log if e["type"] == "other"]
        self.assertEqual(len(other_entries), 1)
        self.assertEqual(other_entries[0]["channel"], "VK")
        self.assertEqual(other_entries[0]["author_name"], "Иванов")
        self.assertEqual(other_entries[0]["type_label"], "Другое (произвольный канал)")

    def test_two_separate_adds_log_two_separate_entries(self):
        """В отличие от плоских полей (где повтор с той же датой не
        логировался), каждое добавление в список — отдельное реальное
        событие, всегда логируется, даже если бы даты совпали."""
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        self.client.post(f"/api/blocking-cases/{case['id']}/other-complaints", json={"filed_at": "2026-08-15", "method": "VK"})
        self.client.post(f"/api/blocking-cases/{case['id']}/other-complaints", json={"filed_at": "2026-08-15", "method": "Meta"})

        with self.client.session_transaction() as sess:
            sess["username"] = "admin1"
            sess["role"] = "admin"
        log = self.client.get("/api/complaint-send-log").get_json()
        other_entries = [e for e in log if e["type"] == "other"]
        self.assertEqual(len(other_entries), 2)


if __name__ == "__main__":
    unittest.main()
