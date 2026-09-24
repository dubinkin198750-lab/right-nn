"""Тест: при обнаружении «постоянно блокируемого» домена он автоматически
добавляется в справочник «Поиск по сайтам» (см. app.py,
_maybe_add_chronic_domain_to_site_directory)."""
import os
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


class TestChronicSiteDirectory(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def _wait_until(self, predicate, timeout=5, interval=0.05):
        start = time.time()
        while time.time() - start < timeout:
            if predicate():
                return True
            time.sleep(interval)
        return False

    def test_domain_added_to_site_directory_when_becomes_chronic(self):
        net_lookup = {"ip": "", "defendant": "", "defendant_email": "", "defendant_address": ""}
        with patch("backend.netinfo.lookup", return_value=net_lookup), \
             patch("backend.app.screenshot_capture.capture", side_effect=Exception("no real browser in tests")):
            self.client.post("/api/blocking-cases", json={
                "url": "https://s1.autosite-test.me/a", "author_name": "Автор", "work_title": "Курс", "title": "т",
            })
            # После первой ссылки домен ещё не хронический — в справочник не добавлен
            self.assertFalse(any("autosite-test.me" in s["url_template"] for s in storage.load_sites()))

            self.client.post("/api/blocking-cases", json={
                "url": "https://s2.autosite-test.me/b", "author_name": "Автор", "work_title": "Курс", "title": "т",
            })

        self.assertTrue(self._wait_until(lambda: any("autosite-test.me" in s["url_template"] for s in storage.load_sites())),
                         "домен не появился в справочнике «Поиск по сайтам» после того, как стал хроническим")
        matching = [s for s in storage.load_sites() if "autosite-test.me" in s["url_template"]]
        self.assertEqual(len(matching), 1)  # ровно одна запись, не задвоена
        self.assertEqual(matching[0]["type"], "auto")

    def test_domain_not_duplicated_if_already_in_directory_under_different_subdomain(self):
        """Если домен уже есть в справочнике (пусть даже под другим
        поддоменом с тем же базовым доменом) — новую запись создавать не
        нужно."""
        storage.upsert_site({"id": None, "name": "уже есть", "url_template": "https://old.dup-test.me", "type": "auto"})
        baseline_count = len(storage.load_sites())

        net_lookup = {"ip": "", "defendant": "", "defendant_email": "", "defendant_address": ""}
        with patch("backend.netinfo.lookup", return_value=net_lookup), \
             patch("backend.app.screenshot_capture.capture", side_effect=Exception("no real browser in tests")):
            self.client.post("/api/blocking-cases", json={
                "url": "https://s1.dup-test.me/a", "author_name": "Автор", "work_title": "Курс", "title": "т",
            })
            self.client.post("/api/blocking-cases", json={
                "url": "https://s2.dup-test.me/b", "author_name": "Автор", "work_title": "Курс", "title": "т",
            })

        time.sleep(0.3)
        self.assertEqual(len(storage.load_sites()), baseline_count)  # ничего не добавилось поверх исходной записи
        self.assertEqual(len([s for s in storage.load_sites() if "dup-test.me" in s["url_template"]]), 1)

    def test_single_link_below_threshold_not_added(self):
        baseline_count = len(storage.load_sites())
        with patch("backend.netinfo.lookup", return_value={"ip": "", "defendant": "", "defendant_email": "", "defendant_address": ""}):
            self.client.post("/api/blocking-cases", json={
                "url": "https://onesite-test.example/x", "author_name": "Автор", "work_title": "Курс", "title": "т",
            })
        time.sleep(0.2)
        self.assertEqual(len(storage.load_sites()), baseline_count)


if __name__ == "__main__":
    unittest.main()
