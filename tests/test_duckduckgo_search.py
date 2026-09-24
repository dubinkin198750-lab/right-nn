import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402
from backend import duckduckgo_search as ddg  # noqa: E402


_SAMPLE_HTML = """
<div class="results">
  <div class="result web-result">
    <h2 class="result__title">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpirate1.test%2Fcourse&rut=abc">Курс — скачать бесплатно</a>
    </h2>
    <a class="result__snippet">Скачать <b>курс</b> бесплатно, раздача.</a>
  </div>
  <div class="result web-result">
    <h2 class="result__title">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpirate2.test%2Fthreads%2F123&rut=def">Ещё раздача</a>
    </h2>
    <a class="result__snippet">Второй результат.</a>
  </div>
</div>
"""


class TestIsConfigured(unittest.TestCase):
    def test_always_true_no_credentials_needed(self):
        """В отличие от Yandex/Google — ключ тут не нужен вообще."""
        self.assertTrue(ddg.is_configured())


class TestDecodeRedirect(unittest.TestCase):
    def test_decodes_uddg_wrapped_url(self):
        wrapped = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage&rut=abc123"
        self.assertEqual(ddg._decode_ddg_redirect(wrapped), "https://example.com/page")

    def test_plain_url_passed_through(self):
        self.assertEqual(ddg._decode_ddg_redirect("https://example.com/x"), "https://example.com/x")

    def test_empty_returns_empty(self):
        self.assertEqual(ddg._decode_ddg_redirect(""), "")

    def test_protocol_relative_without_uddg_gets_https_prefix(self):
        self.assertEqual(ddg._decode_ddg_redirect("//example.com/x"), "https://example.com/x")


class TestParseOrganicHtml(unittest.TestCase):
    def test_extracts_title_url_description(self):
        results = ddg._parse_organic_html(_SAMPLE_HTML)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["url"], "https://pirate1.test/course")
        self.assertEqual(results[0]["title"], "Курс — скачать бесплатно")
        self.assertIn("курс", results[0]["description"])

    def test_strips_html_tags_from_snippet(self):
        results = ddg._parse_organic_html(_SAMPLE_HTML)
        self.assertNotIn("<b>", results[0]["description"])

    def test_second_result_decoded_correctly(self):
        results = ddg._parse_organic_html(_SAMPLE_HTML)
        self.assertEqual(results[1]["url"], "https://pirate2.test/threads/123")

    def test_positions_are_sequential(self):
        results = ddg._parse_organic_html(_SAMPLE_HTML)
        self.assertEqual([r["position"] for r in results], [1, 2])

    def test_empty_html_returns_empty_list(self):
        self.assertEqual(ddg._parse_organic_html(""), [])

    def test_fallback_parses_plain_external_links_when_markup_unrecognized(self):
        """Если DuckDuckGo сменит вёрстку и основной разбор ничего не найдёт —
        запасной вариант всё равно должен вернуть хоть что-то полезное."""
        html = '<a href="https://external.test/page1">x</a><a href="https://duckduckgo.com/settings">y</a>'
        results = ddg._parse_organic_html(html)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://external.test/page1")


class TestSearch(unittest.TestCase):
    def setUp(self):
        self._orig_delay = ddg.PAGE_DELAY_SEC
        ddg.PAGE_DELAY_SEC = 0  # не ждать реально в тестах

    def tearDown(self):
        ddg.PAGE_DELAY_SEC = self._orig_delay

    def test_successful_search_returns_results_and_demo_false(self):
        fake_resp = MagicMock(status_code=200, text=_SAMPLE_HTML)
        with unittest.mock.patch.object(requests.Session, "get", return_value=fake_resp):
            results, demo = ddg.search("тестовый запрос", pages=1)
        self.assertEqual(len(results), 2)
        self.assertFalse(demo)

    def test_non_200_status_raises_after_all_pages_fail(self):
        fake_resp = MagicMock(status_code=403, text="blocked")
        with unittest.mock.patch.object(requests.Session, "get", return_value=fake_resp):
            with self.assertRaises(ddg.DuckDuckGoSearchError):
                ddg.search("запрос", pages=1)

    def test_partial_failure_across_pages_still_returns_what_succeeded(self):
        """Одна страница не удалась (например, временная блокировка), но не
        все — как и у Yandex, не должно ронять уже полученные результаты."""
        ok_resp = MagicMock(status_code=200, text=_SAMPLE_HTML)
        bad_resp = MagicMock(status_code=403, text="blocked")
        with unittest.mock.patch.object(requests.Session, "get", side_effect=[ok_resp, bad_resp]):
            results, demo = ddg.search("запрос", pages=2)
        self.assertEqual(len(results), 2)  # с первой страницы

    def test_should_stop_halts_early(self):
        fake_resp = MagicMock(status_code=200, text=_SAMPLE_HTML)
        calls = {"n": 0}

        def fake_stop():
            calls["n"] += 1
            return calls["n"] > 1  # останавливаемся после первой проверки прошла

        with unittest.mock.patch.object(requests.Session, "get", return_value=fake_resp):
            results, demo = ddg.search("запрос", pages=5, should_stop=fake_stop)
        self.assertLess(len(results), 10)  # не успело пройти все 5 страниц

    def test_offset_parameter_increases_with_page(self):
        """Страница 2 должна запрашиваться со смещением (параметр s),
        не той же самой первой страницей повторно."""
        fake_resp = MagicMock(status_code=200, text=_SAMPLE_HTML)
        captured_params = []

        def fake_get(url, params=None, **kwargs):
            captured_params.append(params)
            return fake_resp

        with unittest.mock.patch.object(requests.Session, "get", side_effect=fake_get):
            ddg.search("запрос", pages=2)
        self.assertNotIn("s", captured_params[0])  # первая страница — без смещения
        self.assertEqual(captured_params[1]["s"], ddg.RESULTS_PER_PAGE)  # вторая — со смещением


_SAMPLE_SERPAPI_RESPONSE = {
    "search_metadata": {"status": "Success"},
    "organic_results": [
        {"position": 1, "title": "Курс — платный резерв", "link": "https://pirate1.test/course", "snippet": "Найдено через SerpApi"},
        {"position": 2, "title": "Ещё раздача", "link": "https://pirate2.test/threads/123", "snippet": "Второй результат"},
    ],
}


class TestIsSerpapiFallbackConfigured(unittest.TestCase):
    def test_false_without_env_var(self):
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(ddg.is_serpapi_fallback_configured())

    def test_true_with_env_var(self):
        with unittest.mock.patch.dict(os.environ, {"SERPAPI_KEY": "test-key-123"}):
            self.assertTrue(ddg.is_serpapi_fallback_configured())


class TestSerpApiFallback(unittest.TestCase):
    """Пункт из запроса пользователя: платный резерв (SerpApi, тот же
    движок duckduckgo) — переключаемся на него, если бесплатный скрейпинг
    заблокирован целиком, но НЕ если он частично сработал (не мешаем
    результаты из двух разных источников в одном ответе)."""

    def setUp(self):
        self._orig_delay = ddg.PAGE_DELAY_SEC
        ddg.PAGE_DELAY_SEC = 0
        self._env_patcher = unittest.mock.patch.dict(os.environ, {"SERPAPI_KEY": "test-key-123"})
        self._env_patcher.start()

    def tearDown(self):
        ddg.PAGE_DELAY_SEC = self._orig_delay
        self._env_patcher.stop()

    def test_fallback_not_used_without_key_configured(self):
        """Без ключа — поведение точно такое же, как раньше: полный отказ
        поднимается как обычная ошибка, резерв даже не пытается сработать."""
        self._env_patcher.stop()  # выключаю ключ именно для этого теста
        try:
            bad_resp = MagicMock(status_code=403, text="blocked")
            with unittest.mock.patch.object(requests.Session, "get", return_value=bad_resp):
                with self.assertRaises(ddg.DuckDuckGoSearchError):
                    ddg.search("запрос", pages=1)
        finally:
            self._env_patcher.start()

    def test_fallback_kicks_in_when_all_pages_blocked(self):
        blocked_resp = MagicMock(status_code=403, text="blocked")
        serpapi_resp = MagicMock(status_code=200)
        serpapi_resp.json.return_value = _SAMPLE_SERPAPI_RESPONSE

        call_log = []

        def fake_get(url, params=None, **kwargs):
            call_log.append(url)
            if url == ddg.SERPAPI_URL:
                return serpapi_resp
            return blocked_resp

        with unittest.mock.patch.object(requests.Session, "get", side_effect=fake_get):
            results, demo = ddg.search("запрос", pages=1)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["url"], "https://pirate1.test/course")
        self.assertEqual(results[0]["description"], "Найдено через SerpApi")
        self.assertFalse(demo)
        self.assertIn(ddg.SERPAPI_URL, call_log)  # резерв реально был вызван

    def test_fallback_not_used_when_scraping_partially_succeeds(self):
        """Ключевая суть решения: если бесплатный путь сработал хотя бы
        частично — не подмешиваем платный резерв, отдаём как есть."""
        ok_resp = MagicMock(status_code=200, text=_SAMPLE_HTML)
        bad_resp = MagicMock(status_code=403, text="blocked")
        call_log = []

        def fake_get(url, params=None, **kwargs):
            call_log.append(url)
            if url == ddg.SERPAPI_URL:
                return MagicMock(status_code=200, json=lambda: _SAMPLE_SERPAPI_RESPONSE)
            return ok_resp if params.get("s") is None else bad_resp

        with unittest.mock.patch.object(requests.Session, "get", side_effect=fake_get):
            results, demo = ddg.search("запрос", pages=2)

        self.assertEqual(len(results), 2)  # только со страницы 1, которая прошла
        self.assertNotIn(ddg.SERPAPI_URL, call_log)  # резерв не вызывался

    def test_both_scraping_and_fallback_fail_gives_combined_error(self):
        blocked_resp = MagicMock(status_code=403, text="blocked")
        serpapi_error_resp = MagicMock(status_code=200)
        serpapi_error_resp.json.return_value = {"search_metadata": {"status": "Error"}, "error": "Invalid API key"}

        def fake_get(url, params=None, **kwargs):
            return serpapi_error_resp if url == ddg.SERPAPI_URL else blocked_resp

        with unittest.mock.patch.object(requests.Session, "get", side_effect=fake_get):
            with self.assertRaises(ddg.DuckDuckGoSearchError) as ctx:
                ddg.search("запрос", pages=1)
        self.assertIn("SerpApi", str(ctx.exception))

    def test_serpapi_error_status_in_body_raises_even_with_200(self):
        """SerpApi может вернуть HTTP 200, но с ошибкой внутри тела
        ответа (search_metadata.status == "Error") — это тоже сбой,
        не просто пустой список результатов."""
        error_resp = MagicMock(status_code=200)
        error_resp.json.return_value = {"search_metadata": {"status": "Error"}, "error": "Invalid API key"}
        session = requests.Session()
        with unittest.mock.patch.object(requests.Session, "get", return_value=error_resp):
            with self.assertRaises(ddg.DuckDuckGoSearchError):
                ddg._search_one_page_via_serpapi("запрос", 1, session)

    def test_serpapi_page_offset_uses_start_parameter(self):
        captured = []

        def fake_get(url, params=None, **kwargs):
            captured.append(params)
            return MagicMock(status_code=200, json=lambda: _SAMPLE_SERPAPI_RESPONSE)

        session = requests.Session()
        with unittest.mock.patch.object(requests.Session, "get", side_effect=fake_get):
            ddg._search_one_page_via_serpapi("запрос", 2, session)
        self.assertEqual(captured[0]["start"], ddg.SERPAPI_RESULTS_PER_PAGE)


if __name__ == "__main__":
    unittest.main()
