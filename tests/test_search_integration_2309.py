"""Обновление 23.09: новые источники подключаются, не меняя работу старых."""
import base64
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import search_sources, yandex_search, vk_search, torznab_search, site_search, storage  # noqa: E402

YANDEX_ITEMS = [
    {"position": 1, "title": "Фабрика клонов — слив", "url": "https://s66.zapret.me/t/1", "description": "Андрианов"},
    {"position": 2, "title": "Курс", "url": "https://a.test/2", "description": ""},
]


class TestDefaultBehaviourUnchanged(unittest.TestCase):
    """Контрольный набор: с настройками по умолчанию результат поиска такой же,
    как до обновления (те же ссылки, тот же порядок, те же поля)."""

    def test_yandex_only_same_items(self):
        with patch.object(yandex_search, "search", return_value=([dict(i) for i in YANDEX_ITEMS], False)):
            items, demo = search_sources.run_search("Андрианов", 1, {"yandex": True})
        self.assertEqual([i["url"] for i in items], [i["url"] for i in YANDEX_ITEMS])
        self.assertTrue(all(i["source"] == "Яндекс" for i in items))
        self.assertFalse(demo)

    def test_report_is_optional(self):
        with patch.object(yandex_search, "search", return_value=([dict(i) for i in YANDEX_ITEMS], False)):
            a, _ = search_sources.run_search("x", 1, {"yandex": True})
            report = {}
            b, _ = search_sources.run_search("x", 1, {"yandex": True}, report=report)
        self.assertEqual(a, b)
        self.assertEqual(report["Яндекс"]["found"], 2)
        self.assertEqual(report["Яндекс"]["status"], "ok")

    def test_new_sources_off_by_default(self):
        tasks = search_sources.build_tasks("x", {"yandex": True})
        self.assertEqual([t[0] for t in tasks], ["yandex"])


class TestGoogleDemoBlocked(unittest.TestCase):
    def test_google_without_key_skipped_when_yandex_configured(self):
        with patch.object(yandex_search, "is_configured", return_value=True), \
             patch.object(search_sources, "is_google_configured", return_value=False), \
             patch.object(yandex_search, "search", return_value=([dict(YANDEX_ITEMS[0])], False)), \
             patch("backend.google_search.search") as g:
            report = {}
            items, _ = search_sources.run_search("x", 1, {"yandex": True, "google": True}, report=report)
        g.assert_not_called()
        self.assertEqual(report["Google"]["status"], "not_configured")
        self.assertTrue(all(i["source"] != "Google" for i in items))

    def test_only_unconfigured_source_does_not_raise(self):
        with patch.object(yandex_search, "is_configured", return_value=True), \
             patch.object(search_sources, "is_google_configured", return_value=False):
            report = {}
            items, _ = search_sources.run_search("x", 1, {"google": True}, report=report)
        self.assertEqual(items, [])

    def test_full_demo_install_still_works(self):
        """Без единого ключа (локальная демонстрация) всё по-старому."""
        with patch.object(yandex_search, "is_configured", return_value=False), \
             patch.object(search_sources, "is_google_configured", return_value=False):
            self.assertTrue(search_sources.source_available("google")[0])


class TestNewSourcesIsolation(unittest.TestCase):
    def test_failing_vk_does_not_break_yandex(self):
        with patch.dict(os.environ, {"VK_SERVICE_TOKEN": "t"}), \
             patch.object(yandex_search, "search", return_value=([dict(YANDEX_ITEMS[0])], False)), \
             patch.object(vk_search, "search_posts", side_effect=vk_search.VkSearchError("VK: слишком много запросов (код 6)")):
            report = {}
            items, _ = search_sources.run_search("x", 1, {"yandex": True, "vk": True}, report=report)
        self.assertEqual(len(items), 1)
        self.assertEqual(report["VK: записи"]["status"], "error")

    def test_vk_not_configured(self):
        with patch.dict(os.environ, {"VK_SERVICE_TOKEN": ""}):
            report = {}
            search_sources.run_search("x", 1, {"vk": True}, report=report)
        self.assertEqual(report["VK: записи"]["status"], "not_configured")


class TestVk(unittest.TestCase):
    def _resp(self, payload):
        m = MagicMock()
        m.json.return_value = payload
        return m

    def test_posts_parsed(self):
        payload = {"response": {"items": [{"owner_id": -123, "id": 45, "text": "Андрианов курс\nслив"}]}}
        with patch.dict(os.environ, {"VK_SERVICE_TOKEN": "t"}), patch("requests.get", return_value=self._resp(payload)):
            items, demo = vk_search.search_posts("Андрианов", 1)
        self.assertEqual(items[0]["url"], "https://vk.com/wall-123_45")
        self.assertEqual(items[0]["title"], "Андрианов курс")

    def test_empty_retried(self):
        empty = self._resp({"response": {"items": []}})
        full = self._resp({"response": {"items": [{"owner_id": 1, "id": 2, "text": "x"}]}})
        with patch.dict(os.environ, {"VK_SERVICE_TOKEN": "t"}), patch.object(vk_search, "EMPTY_RETRY_DELAY_SEC", 0), \
             patch("requests.get", side_effect=[empty, full]) as g:
            items, _ = vk_search.search_posts("x", 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(g.call_count, 2)

    def test_error_readable(self):
        with patch.dict(os.environ, {"VK_SERVICE_TOKEN": "t"}), \
             patch("requests.get", return_value=self._resp({"error": {"error_code": 5, "error_msg": "auth"}})):
            with self.assertRaises(vk_search.VkSearchError) as cm:
                vk_search.search_posts("x", 1)
        self.assertIn("неверный", str(cm.exception))


class TestTorznab(unittest.TestCase):
    def test_error_element(self):
        with self.assertRaises(torznab_search.TorznabSearchError):
            torznab_search.parse('<error code="100" description="Invalid API Key"/>')

    def test_search_uses_page_link_not_download(self):
        xml = ('<rss><channel><item><title>Курс</title><comments>https://tracker/t/1</comments>'
               '<link>http://127.0.0.1:9117/dl/1</link></item></channel></rss>')
        m = MagicMock(status_code=200, text=xml)
        with patch.dict(os.environ, {"TORZNAB_URL": "http://127.0.0.1:9117/api"}), patch("requests.get", return_value=m):
            items, _ = torznab_search.search("Курс", 1)
        self.assertEqual(items[0]["url"], "https://tracker/t/1")


def _op(raw_text):
    return {"done": True, "response": {"rawData": base64.b64encode(raw_text.encode()).decode()}}


XML_OK = ('<yandexsearch><response><found priority="all">5</found><results><grouping><group><doc>'
          '<url>https://s66.zapret.me/t/1</url><title>Слив</title></doc></group></grouping></results></response></yandexsearch>')
XML_BROKEN = '<yandexsearch><response><found priority="all">5</found><results/></response></yandexsearch>'
HTML = '<li class="serp-item"><h2><a href="https://s66.zapret.me/t/1">Слив</a></h2></li>'


class TestYandexFormats(IsolatedStorageTestCase):
    def _run(self, mode, bodies):
        calls = iter(bodies)
        with patch.dict(os.environ, {"YANDEX_RESPONSE_FORMAT": mode}), \
             patch.object(yandex_search, "_fetch_raw", side_effect=lambda q, p, s, fmt="FORMAT_HTML": next(calls)):
            return yandex_search._search_one_page_real("x", 1, None)

    def test_default_is_html(self):
        with patch.dict(os.environ, {"YANDEX_RESPONSE_FORMAT": ""}):
            self.assertEqual(yandex_search.response_format_mode(), "html")

    def test_html_mode_unchanged(self):
        self.assertEqual(self._run("html", [HTML])[0]["url"], "https://s66.zapret.me/t/1")
        self.assertEqual(storage.load_yandex_compare(), [])

    def test_compare_returns_html_and_logs(self):
        res = self._run("compare", [HTML, XML_OK])
        self.assertEqual(res[0]["url"], "https://s66.zapret.me/t/1")
        log = storage.load_yandex_compare()
        self.assertEqual(log[0]["html_count"], 1)
        self.assertEqual(log[0]["xml_count"], 1)

    def test_compare_xml_failure_does_not_affect_result(self):
        res = self._run("compare", [HTML, "не xml"])
        self.assertEqual(len(res), 1)
        self.assertIsNone(storage.load_yandex_compare()[0]["xml_count"])

    def test_xml_parse_failure_is_an_error_not_empty(self):
        with self.assertRaises(yandex_search.YandexSearchError) as cm:
            self._run("xml", [XML_BROKEN])
        self.assertIn("Сбой разбора", str(cm.exception))

    def test_xml_no_results_code_is_empty(self):
        res = self._run("xml", ['<yandexsearch><response><error code="15">нет</error></response></yandexsearch>'])
        self.assertEqual(res, [])


class TestSiteModes(unittest.TestCase):
    def test_old_sites_behave_as_before(self):
        self.assertEqual(site_search.site_mode({"type": "auto"}), "auto")
        self.assertEqual(site_search.site_mode({"type": "xenforo"}), "xenforo")
        self.assertEqual(site_search.site_mode({}), "auto")

    def test_manual_and_off_not_searched(self):
        sites = [{"id": "a", "name": "A", "url_template": "https://a.test/?q={query}", "mode": "manual"},
                 {"id": "b", "name": "B", "url_template": "https://b.test/?q={query}", "mode": "off"},
                 {"id": "c", "name": "C", "url_template": "https://c.test/?q={query}"}]
        report = {}
        with patch.object(site_search, "search_one_site", return_value=[]) as m:
            site_search.search_sites(sites, ["x"], report=report)
        self.assertEqual(m.call_count, 1)
        self.assertEqual(report["a"]["status"], "skipped")
        self.assertEqual(report["c"]["status"], "empty")

    def test_no_template_status(self):
        site = {"id": "a", "name": "A", "url_template": "https://a.test"}
        report = {}
        with patch.object(site_search, "search_xenforo", side_effect=site_search.SiteTypeNotSupportedError("нет")):
            site_search.search_sites([site], ["x"], report=report)
        self.assertEqual(report["a"]["status"], "no_template")

    def test_error_classification(self):
        self.assertEqual(site_search.classify_error("Не удалось загрузить: 403 Client Error: Forbidden"), "blocked")
        self.assertEqual(site_search.classify_error("Сайт не ответил за 20 секунд"), "unavailable")
        self.assertEqual(site_search.classify_error("что-то ещё"), "error")


class TestSiteApi(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as s:
            s["username"], s["role"] = "admin1", "admin"

    def test_create_and_update_optional_fields(self):
        site = self.client.post("/api/sites", json={"name": "a", "url_template": "https://a.test/?q={query}",
                                                    "mode": "template", "priority": "high"}).get_json()
        self.assertEqual(site["mode"], "template")
        r = self.client.put(f"/api/sites/{site['id']}", json={"notes": "заметка", "mirrors": ["a2.test"]}).get_json()
        self.assertEqual(r["notes"], "заметка")
        self.assertEqual(r["mirrors"], ["a2.test"])
        self.assertEqual(r["mode"], "template")

    def test_invalid_mode_rejected(self):
        site = self.client.post("/api/sites", json={"name": "a", "url_template": "https://a.test"}).get_json()
        self.assertEqual(self.client.put(f"/api/sites/{site['id']}", json={"mode": "x"}).status_code, 400)

    def test_test_endpoint_reports_status(self):
        site = self.client.post("/api/sites", json={"name": "a", "url_template": "https://a.test/?q={query}"}).get_json()
        with patch.object(site_search, "search_one_site", return_value=[{"url": "https://a.test/t/1", "title": "t"}]):
            r = self.client.post(f"/api/sites/{site['id']}/test", json={"query": "x"}).get_json()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["found"], 1)
        self.assertEqual(storage.get_site(site["id"])["last_status"], "ok")

    def test_redirect_keeps_old_domain_as_mirror(self):
        site = self.client.post("/api/sites", json={"name": "a", "url_template": "https://old.test/s/?q={query}"}).get_json()
        r = self.client.post(f"/api/sites/{site['id']}/apply-redirect", json={"new_domain": "new.test"}).get_json()
        self.assertEqual(r["url_template"], "https://new.test/s/?q={query}")
        self.assertIn("old.test", r["mirrors"])

    def test_cert_status_not_monitored_without_letsencrypt(self):
        with patch("os.path.exists", return_value=False):
            r = self.client.get("/api/admin/cert-status").get_json()
        self.assertFalse(r["monitored"])


if __name__ == "__main__":
    unittest.main()
