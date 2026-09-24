import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import site_search  # noqa: E402


class TestSearchAutoErrorDistinction(unittest.TestCase):
    """Регрессия: при массовом прогоне по большому справочнику сайтов (150+)
    нужно отличать «сайт недоступен» (реальная ошибка, стоит показать) от
    «сайт просто не XenForo и нет known-шаблона» (норма, не ошибка) —
    иначе либо все сбои тихо пропадают, либо почти весь справочник выглядит
    «сломанным», хотя на самом деле просто не подходит под автоопределение."""

    def _site(self, url_template="https://example-forum.test"):
        return {"id": "s1", "name": "Тестовый сайт", "url_template": url_template}

    @patch("backend.site_search.requests.Session")
    def test_not_xenforo_site_returns_empty_without_raising(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session
        form_resp = MagicMock(status_code=200, text="<html>обычная страница без токена</html>")
        form_resp.raise_for_status = MagicMock()
        form_resp.url = "https://example-forum.test/search/"
        session.get.return_value = form_resp

        result = site_search.search_auto(self._site(), "запрос")
        self.assertEqual(result, [])  # тихо пусто, БЕЗ исключения

    @patch("backend.site_search.requests.Session")
    def test_genuine_connectivity_failure_raises_error(self, mock_session_cls):
        import requests
        session = MagicMock()
        mock_session_cls.return_value = session
        session.get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        with self.assertRaises(site_search.SiteSearchError) as ctx:
            site_search.search_auto(self._site(), "запрос")
        self.assertNotIsInstance(ctx.exception, site_search.SiteTypeNotSupportedError)

    @patch("backend.site_search.requests.Session")
    def test_timeout_raises_error_not_swallowed(self, mock_session_cls):
        import requests
        session = MagicMock()
        mock_session_cls.return_value = session
        session.get.side_effect = requests.Timeout()

        with self.assertRaises(site_search.SiteSearchError):
            site_search.search_auto(self._site(), "запрос")

    def test_site_type_not_supported_is_subclass_of_site_search_error(self):
        # на случай, если где-то в коде ловят общий SiteSearchError —
        # специфичный тип всё равно должен ловиться тем же except
        self.assertTrue(issubclass(site_search.SiteTypeNotSupportedError, site_search.SiteSearchError))


class TestSearchGenericFollowsRedirect(unittest.TestCase):
    """Регрессия: если сайт целиком редиректит на другой домен, относительные
    ссылки должны разрешаться от адреса ПОСЛЕ редиректа, иначе получаются
    ссылки на старый, уже неработающий домен."""

    def _site(self, url_template):
        return {"id": "s1", "name": "Тестовый сайт", "url_template": url_template}

    @patch("backend.site_search.requests.get")
    def test_relative_links_resolved_against_final_url_after_redirect(self, mock_get):
        resp = MagicMock(status_code=200)
        resp.raise_for_status = MagicMock()
        resp.url = "https://newdomain.test/search?q=запрос"  # адрес ПОСЛЕ редиректа
        resp.text = '<a href="/threads/course-запрос.123/">Курс запрос — раздача</a>'
        mock_get.return_value = resp

        results = site_search.search_generic(
            self._site("https://olddomain.test/search?q={query}"), "запрос"
        )
        self.assertEqual(len(results), 1)
        # ссылка должна собраться на НОВОМ домене, а не на старом
        self.assertTrue(results[0]["url"].startswith("https://newdomain.test/"))
        self.assertNotIn("olddomain.test", results[0]["url"])

    @patch("backend.site_search.requests.get")
    def test_domain_unchanged_case_still_works_normally(self, mock_get):
        resp = MagicMock(status_code=200)
        resp.raise_for_status = MagicMock()
        resp.url = "https://samedomain.test/search?q=запрос"
        resp.text = '<a href="/threads/course-запрос.123/">Курс запрос — раздача</a>'
        mock_get.return_value = resp

        results = site_search.search_generic(
            self._site("https://samedomain.test/search?q={query}"), "запрос"
        )
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["url"].startswith("https://samedomain.test/"))


class TestDomainRedirectDetection(unittest.TestCase):
    """Отдельно от разрешения ссылок — обнаружение и подсветка самого факта
    «сайт целиком переехал на другой домен», чтобы можно было обновить
    справочник в один клик вместо того, чтобы результаты молча указывали
    на новый домен без объяснений."""

    def test_detects_domain_change(self):
        site = {"url_template": "https://olddomain.test/search?q={query}"}
        results = [{"url": "https://newdomain.test/threads/x.1/", "title": "т"}]
        new_domain = site_search._detect_domain_redirect(site, results)
        self.assertEqual(new_domain, "newdomain.test")

    def test_no_detection_when_domain_matches(self):
        site = {"url_template": "https://samedomain.test/search?q={query}"}
        results = [{"url": "https://samedomain.test/threads/x.1/", "title": "т"}]
        self.assertIsNone(site_search._detect_domain_redirect(site, results))

    def test_no_detection_when_results_span_multiple_domains(self):
        # неоднозначно (например, часть ссылок — внешняя реклама) — не рискуем
        site = {"url_template": "https://olddomain.test/search?q={query}"}
        results = [
            {"url": "https://newdomain.test/threads/x.1/", "title": "т"},
            {"url": "https://another.test/threads/y.1/", "title": "т2"},
        ]
        self.assertIsNone(site_search._detect_domain_redirect(site, results))

    def test_no_detection_on_empty_results(self):
        site = {"url_template": "https://olddomain.test/search?q={query}"}
        self.assertIsNone(site_search._detect_domain_redirect(site, []))

    def test_www_prefix_ignored_in_comparison(self):
        site = {"url_template": "https://www.samedomain.test/search?q={query}"}
        results = [{"url": "https://samedomain.test/threads/x.1/", "title": "т"}]
        self.assertIsNone(site_search._detect_domain_redirect(site, results))


class TestSearchSitesMultiQuery(unittest.TestCase):
    """Регрессия/новая функциональность: можно ввести сколько угодно
    вариантов запроса за один прогон — каждый сайт проверяется по каждому
    запросу, результаты дедуплицируются по ссылке, ошибки по сайту не
    повторяются для каждого запроса отдельно."""

    def test_single_string_query_still_works(self):
        with patch("backend.site_search.search_one_site") as mock_search:
            mock_search.return_value = [{"url": "https://x.test/1", "title": "т"}]
            sites = [{"id": "s1", "name": "Сайт 1", "url_template": "https://x.test"}]
            results, errors, redirects = site_search.search_sites(sites, "один запрос")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["matched_query"], "один запрос")

    def test_multiple_queries_all_tried_per_site(self):
        call_log = []

        def fake_search(site, query):
            call_log.append((site["id"], query))
            return []

        with patch("backend.site_search.search_one_site", side_effect=fake_search):
            sites = [
                {"id": "s1", "name": "Сайт 1", "url_template": "https://x.test"},
                {"id": "s2", "name": "Сайт 2", "url_template": "https://y.test"},
            ]
            site_search.search_sites(sites, ["запрос1", "запрос2"])
            self.assertEqual(len(call_log), 4)  # 2 сайта × 2 запроса
            self.assertIn(("s1", "запрос1"), call_log)
            self.assertIn(("s1", "запрос2"), call_log)
            self.assertIn(("s2", "запрос1"), call_log)
            self.assertIn(("s2", "запрос2"), call_log)

    def test_same_url_found_by_two_queries_deduplicated(self):
        def fake_search(site, query):
            # оба запроса находят одну и ту же ссылку на одном сайте
            return [{"url": "https://x.test/1", "title": f"найдено по «{query}»"}]

        with patch("backend.site_search.search_one_site", side_effect=fake_search):
            sites = [{"id": "s1", "name": "Сайт 1", "url_template": "https://x.test"}]
            results, errors, redirects = site_search.search_sites(sites, ["запрос1", "запрос2"])
            self.assertEqual(len(results), 1)  # не задвоилось
            self.assertEqual(results[0]["matched_query"], "запрос1")  # первый, кем реально нашлось

    def test_different_urls_from_different_queries_both_kept(self):
        def fake_search(site, query):
            return [{"url": f"https://x.test/{query}", "title": query}]

        with patch("backend.site_search.search_one_site", side_effect=fake_search):
            sites = [{"id": "s1", "name": "Сайт 1", "url_template": "https://x.test"}]
            results, errors, redirects = site_search.search_sites(sites, ["a", "b"])
            self.assertEqual(len(results), 2)

    def test_site_error_reported_once_not_once_per_query(self):
        with patch("backend.site_search.search_one_site") as mock_search:
            mock_search.side_effect = site_search.SiteSearchError("сайт недоступен")
            sites = [{"id": "s1", "name": "Сайт 1", "url_template": "https://x.test"}]
            results, errors, redirects = site_search.search_sites(sites, ["запрос1", "запрос2", "запрос3"])
            self.assertEqual(len(errors), 1)  # не 3 раза одна и та же ошибка

    def test_empty_queries_list_falls_back_to_single_empty_search(self):
        with patch("backend.site_search.search_one_site") as mock_search:
            mock_search.return_value = []
            sites = [{"id": "s1", "name": "Сайт 1", "url_template": "https://x.test"}]
            site_search.search_sites(sites, [])
            self.assertEqual(mock_search.call_count, 1)  # не падает, не зависает на 0 запросах

    def test_progress_total_accounts_for_sites_times_queries(self):
        seen_totals = []

        def cb(idx, total, label):
            seen_totals.append(total)

        with patch("backend.site_search.search_one_site", return_value=[]):
            sites = [
                {"id": "s1", "name": "Сайт 1", "url_template": "https://x.test"},
                {"id": "s2", "name": "Сайт 2", "url_template": "https://y.test"},
            ]
            site_search.search_sites(sites, ["a", "b", "c"], progress_cb=cb)
            self.assertTrue(all(t == 6 for t in seen_totals))  # 2 сайта × 3 запроса


    def test_repeat_visits_to_same_site_are_spaced_by_other_sites(self):
        """Регрессия/защита от блокировки по IP: при нескольких вариантах
        запроса повторные обращения к ОДНОМУ и тому же сайту не должны идти
        подряд одно за другим — между ними должны быть визиты на другие
        сайты. Иначе именно эта "очередь запросов подряд к одному сайту"
        может вызвать бан по IP на стороне самого форума."""
        call_log = []

        def fake_search(site, query):
            call_log.append(site["id"])
            return []

        with patch("backend.site_search.search_one_site", side_effect=fake_search):
            sites = [
                {"id": "s1", "name": "Сайт 1", "url_template": "https://a.test"},
                {"id": "s2", "name": "Сайт 2", "url_template": "https://b.test"},
                {"id": "s3", "name": "Сайт 3", "url_template": "https://c.test"},
            ]
            site_search.search_sites(sites, ["query1", "query2", "query3"])

        # порядок должен быть: s1,s2,s3, s1,s2,s3, s1,s2,s3 —
        # а НЕ s1,s1,s1, s2,s2,s2, s3,s3,s3
        self.assertEqual(call_log, ["s1", "s2", "s3", "s1", "s2", "s3", "s1", "s2", "s3"])
        # явная проверка: между двумя последовательными обращениями к s1
        # должны быть другие сайты, не пусто
        first_s1 = call_log.index("s1")
        second_s1 = call_log.index("s1", first_s1 + 1)
        self.assertGreater(second_s1 - first_s1, 1)


if __name__ == "__main__":
    unittest.main()
