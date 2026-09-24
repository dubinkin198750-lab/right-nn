"""Тесты /api/works/run-all/resumable и /resume — прогресс пакетного
поиска должен переживать «перезапуск сервера» (в тестах это симулируется
тем, что storage — единственный источник правды, никакого состояния в
памяти между вызовами не используется)."""
import os
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


def _wait_until(predicate, timeout=5, interval=0.05):
    start = time.time()
    while time.time() - start < timeout:
        if predicate():
            return True
        time.sleep(interval)
    return False


class TestResumableBulkSearch(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

        self.author = storage.upsert_author({"id": None, "name": "Автор"})
        # в хранилище по умолчанию есть демо-произведение — деактивируем его,
        # чтобы точно считать количество затронутых произведений в тестах
        storage.load_works()  # гарантируем, что файл вообще создан (_ensure_files)
        for w in storage.load_works():
            if w["id"] == "demo-work":
                storage.upsert_work(dict(w, active=False))
        self.works = []
        for i in range(3):
            w = {
                "id": None, "author_id": self.author["id"], "title": f"Произведение {i}",
                "query": f"запрос {i}", "keywords": [], "negative_keywords": [],
                "pages": 1, "extra_blocked_domains": [], "active": True,
                "sources": {"yandex": True, "google": False, "avito": False, "telegram": False},
            }
            self.works.append(storage.upsert_work(w))

    def test_no_resumable_batch_initially(self):
        resp = self.client.get("/api/works/run-all/resumable")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.get_json()["resumable"])

    def test_batch_created_on_run_all(self):
        resp = self.client.post("/api/works/run-all")
        self.assertEqual(resp.status_code, 202)
        body = resp.get_json()
        self.assertIn("batch_id", body)
        self.assertEqual(body["count"], 3)

        batch = storage.load_bulk_search_batch()
        self.assertIsNotNone(batch)
        self.assertEqual(set(batch["work_ids"]), {w["id"] for w in self.works})

    def test_resumable_reflects_partial_completion(self):
        """Симулируем, что часть партии завершилась (как будто одно из трёх
        произведений уже успело обработаться до «падения сервера»)."""
        batch_id = "test-batch"
        storage.start_bulk_search_batch(batch_id, [w["id"] for w in self.works], "всем активным")
        storage.mark_bulk_search_work_finished(batch_id, self.works[0]["id"], "done")

        resp = self.client.get("/api/works/run-all/resumable")
        body = resp.get_json()
        self.assertTrue(body["resumable"])
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["done"], 1)
        self.assertEqual(body["remaining"], 2)

    def test_not_resumable_when_all_done(self):
        batch_id = "test-batch"
        storage.start_bulk_search_batch(batch_id, [w["id"] for w in self.works], "всем активным")
        for w in self.works:
            storage.mark_bulk_search_work_finished(batch_id, w["id"], "done")

        resp = self.client.get("/api/works/run-all/resumable")
        self.assertFalse(resp.get_json()["resumable"])

    def test_resume_only_starts_remaining_works(self):
        from backend import jobs

        batch_id = "test-batch"
        storage.start_bulk_search_batch(batch_id, [w["id"] for w in self.works], "всем активным")
        storage.mark_bulk_search_work_finished(batch_id, self.works[0]["id"], "done")

        orig_start_job = jobs.start_job
        started_work_ids = []

        def spy_start_job(work, author_name="", start_delay=0, on_finish=None):
            started_work_ids.append(work["id"])
            return orig_start_job(work, author_name, 9999, on_finish)  # большая задержка — не даём реально стартовать в тесте

        jobs.start_job = spy_start_job
        try:
            resp = self.client.post("/api/works/run-all/resume")
        finally:
            jobs.start_job = orig_start_job

        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.get_json()["count"], 2)
        self.assertNotIn(self.works[0]["id"], started_work_ids)  # уже готовое — не запускается заново
        self.assertIn(self.works[1]["id"], started_work_ids)
        self.assertIn(self.works[2]["id"], started_work_ids)

    def test_resume_with_nothing_left_returns_400(self):
        batch_id = "test-batch"
        storage.start_bulk_search_batch(batch_id, [w["id"] for w in self.works], "всем активным")
        for w in self.works:
            storage.mark_bulk_search_work_finished(batch_id, w["id"], "done")

        resp = self.client.post("/api/works/run-all/resume")
        self.assertEqual(resp.status_code, 400)

    def test_resume_with_no_batch_returns_404(self):
        resp = self.client.post("/api/works/run-all/resume")
        self.assertEqual(resp.status_code, 404)

    def test_dismiss_clears_batch(self):
        batch_id = "test-batch"
        storage.start_bulk_search_batch(batch_id, [w["id"] for w in self.works], "всем активным")
        storage.mark_bulk_search_work_finished(batch_id, self.works[0]["id"], "done")

        resp = self.client.delete("/api/works/run-all/resumable")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(storage.load_bulk_search_batch())

    def test_resumable_ignores_deleted_or_deactivated_works(self):
        """Если оставшееся произведение успели удалить или деактивировать
        между «падением» и следующим открытием приложения — не должно
        предлагаться продолжить с ним."""
        batch_id = "test-batch"
        storage.start_bulk_search_batch(batch_id, [w["id"] for w in self.works], "всем активным")
        storage.mark_bulk_search_work_finished(batch_id, self.works[0]["id"], "done")
        storage.mark_bulk_search_work_finished(batch_id, self.works[1]["id"], "done")
        # третье не деактивировано — удаляем его
        storage.delete_work(self.works[2]["id"])

        resp = self.client.get("/api/works/run-all/resumable")
        self.assertFalse(resp.get_json()["resumable"])

    def test_end_to_end_via_real_background_jobs(self):
        """Полный цикл через настоящие фоновые задачи (без спая) — запускаем
        партию из 2 произведений, ждём, пока реально завершатся (демо-режим,
        без ключей API — быстро), проверяем, что resumable корректно
        показывает «не осталось ничего»."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("YANDEX_API_KEY", None)
            resp = self.client.post("/api/works/run-all")
        batch_id = resp.get_json()["batch_id"]

        def all_done():
            batch = storage.load_bulk_search_batch()
            done_ids = {wid for wid, s in batch.get("work_status", {}).items() if s.get("status") in ("done", "error")}
            return len(done_ids) == len(self.works)

        self.assertTrue(_wait_until(all_done, timeout=15))
        resp2 = self.client.get("/api/works/run-all/resumable")
        self.assertFalse(resp2.get_json()["resumable"])


if __name__ == "__main__":
    unittest.main()
