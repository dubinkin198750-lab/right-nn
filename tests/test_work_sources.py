"""Тесты POST/GET /api/works — в первую очередь сохранение поля sources.

Регрессия на реальный найденный баг: DuckDuckGo был полностью встроен в
backend/search_sources.py (build_tasks/run_search — юнит-тесты на этом
уровне все проходили), но эндпоинт создания произведения фильтрует
входящие sources через жёстко заданный список ключей (DEFAULT_SOURCES в
app.py и одноимённое поле в storage.py) — DuckDuckGo забыли добавить
туда, из-за чего значение duckduckgo молча выбрасывалось при сохранении,
и вся интеграция была нерабочей несмотря на зелёные юнит-тесты нижнего
уровня. Нашли только сквозной проверкой через реальный HTTP-эндпоинт."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


class TestWorkSourcesPersistence(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def _author(self):
        return storage.upsert_author({"id": None, "name": "Автор"})

    def test_duckduckgo_source_is_saved(self):
        """Ключевая регрессия — раньше duckduckgo молча пропадал."""
        author = self._author()
        resp = self.client.post("/api/works", json={
            "author_id": author["id"], "title": "Курс", "query": "тест",
            "sources": {"yandex": False, "google": False, "duckduckgo": True, "avito": False, "telegram": False},
        })
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.get_json()["sources"]["duckduckgo"])

    def test_all_five_sources_present_in_saved_work(self):
        """Все пять источников должны присутствовать в ответе как ключи —
        не только те, что были True."""
        author = self._author()
        resp = self.client.post("/api/works", json={
            "author_id": author["id"], "title": "Курс", "query": "тест",
            "sources": {"yandex": True},
        })
        sources = resp.get_json()["sources"]
        # 23.09: добавлены три новых источника, по умолчанию выключены
        self.assertEqual(set(sources.keys()), {"yandex", "google", "duckduckgo", "avito", "telegram",
                                               "vk", "vk_video", "torrents"})
        self.assertFalse(sources["vk"] or sources["vk_video"] or sources["torrents"])

    def test_default_work_without_explicit_sources_includes_duckduckgo_key(self):
        """Дефолтное произведение (sources не передали вовсе) — ключ
        duckduckgo всё равно должен присутствовать (False), не отсутствовать."""
        author = self._author()
        resp = self.client.post("/api/works", json={"author_id": author["id"], "title": "Курс", "query": "тест"})
        sources = resp.get_json()["sources"]
        self.assertIn("duckduckgo", sources)
        self.assertFalse(sources["duckduckgo"])

    def test_update_work_preserves_duckduckgo_true(self):
        author = self._author()
        work = self.client.post("/api/works", json={
            "author_id": author["id"], "title": "Курс", "query": "тест",
            "sources": {"duckduckgo": True},
        }).get_json()
        resp = self.client.put(f"/api/works/{work['id']}", json={
            "title": "Курс (обновлён)", "query": "тест",
            "sources": {"duckduckgo": True, "yandex": True},
        })
        self.assertTrue(resp.get_json()["sources"]["duckduckgo"])


if __name__ == "__main__":
    unittest.main()
