import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import jobs, yandex_search  # noqa: E402


def _wait_until(predicate, timeout=5, interval=0.05):
    start = time.time()
    while time.time() - start < timeout:
        if predicate():
            return True
        time.sleep(interval)
    return False


class TestCancelWorkJob(IsolatedStorageTestCase):
    """Кнопка «Остановить поиск» у отдельного произведения."""

    def setUp(self):
        super().setUp()
        os.environ["YANDEX_API_KEY"] = "test"
        os.environ["YANDEX_FOLDER_ID"] = "test"
        self._orig_page_delay = yandex_search.PAGE_DELAY_SEC
        yandex_search.PAGE_DELAY_SEC = 0.3  # достаточно медленно, чтобы успеть отменить между страницами

    def tearDown(self):
        yandex_search.PAGE_DELAY_SEC = self._orig_page_delay
        os.environ.pop("YANDEX_API_KEY", None)
        os.environ.pop("YANDEX_FOLDER_ID", None)
        super().tearDown()

    def _work(self, pages=10):
        return {
            "id": "test-work", "author_id": "demo-author", "title": "Тестовое произведение",
            "query": "тестовый запрос", "keywords": [], "negative_keywords": [],
            "pages": pages, "extra_blocked_domains": [], "active": True,
            "sources": {"yandex": True, "google": False, "avito": False, "telegram": False},
        }

    def test_cancel_running_job_ends_with_cancelled_status(self):
        def slow_page(query_text, page, session):
            return [{"url": f"https://x.test/{page}", "title": "т"}]

        orig = yandex_search._search_one_page_real
        yandex_search._search_one_page_real = slow_page
        try:
            job_id = jobs.start_job(self._work(pages=10), "Автор")
            self.assertTrue(_wait_until(lambda: jobs.get_job(job_id)["status"] == "running"))

            jobs.cancel_job(job_id)

            self.assertTrue(_wait_until(lambda: jobs.get_job(job_id)["status"] in ("cancelled", "done", "error")))
            job = jobs.get_job(job_id)
            self.assertEqual(job["status"], "cancelled")
        finally:
            yandex_search._search_one_page_real = orig

    def test_cancel_does_not_lose_results_found_before_stopping(self):
        def slow_page(query_text, page, session):
            return [{"url": f"https://x.test/{page}", "title": f"курс {page}", "description": ""}]

        orig = yandex_search._search_one_page_real
        yandex_search._search_one_page_real = slow_page
        try:
            job_id = jobs.start_job(self._work(pages=10), "Автор")
            self.assertTrue(_wait_until(lambda: jobs.get_job(job_id)["status"] == "running"))
            time.sleep(0.5)  # дать пройти паре страниц
            jobs.cancel_job(job_id)
            self.assertTrue(_wait_until(lambda: jobs.get_job(job_id)["status"] == "cancelled"))

            job = jobs.get_job(job_id)
            self.assertIsNotNone(job["result"])
            self.assertGreater(job["result"]["raw_count"], 0)  # что-то успело найтись
        finally:
            yandex_search._search_one_page_real = orig

    def test_cancel_queued_job_stops_before_it_ever_runs(self):
        """Задача с большой задержкой старта (массовый запуск) — отмена
        должна сработать быстро, не дожидаясь конца всей задержки."""
        job_id = jobs.start_job(self._work(pages=1), "Автор", start_delay=30)
        time.sleep(0.1)
        self.assertEqual(jobs.get_job(job_id)["status"], "queued")

        jobs.cancel_job(job_id)

        # должно завершиться быстро (в пределах пары секунд), а не через 30 секунд
        self.assertTrue(_wait_until(lambda: jobs.get_job(job_id)["status"] == "cancelled", timeout=3))

    def test_cancel_unknown_job_returns_none(self):
        self.assertIsNone(jobs.cancel_job("несуществующий-id"))

    def test_cancel_already_finished_job_is_noop(self):
        job_id = jobs.start_job(self._work(pages=0), "Автор")
        self.assertTrue(_wait_until(lambda: jobs.get_job(job_id)["status"] in ("done", "error", "cancelled")))
        result = jobs.cancel_job(job_id)
        self.assertIsNotNone(result)
        # статус не должен превратиться в cancelled постфактум
        self.assertIn(jobs.get_job(job_id)["status"], ("done", "error"))

    def test_cancel_all_jobs_stops_multiple_at_once(self):
        def slow_page(query_text, page, session):
            return [{"url": f"https://x.test/{page}", "title": "т"}]

        orig = yandex_search._search_one_page_real
        yandex_search._search_one_page_real = slow_page
        try:
            job_ids = [jobs.start_job(self._work(pages=10), "Автор") for _ in range(3)]
            for jid in job_ids:
                self.assertTrue(_wait_until(lambda jid=jid: jobs.get_job(jid)["status"] == "running"))

            cancelled = jobs.cancel_all_jobs()
            self.assertEqual(len(cancelled), 3)

            for jid in job_ids:
                self.assertTrue(_wait_until(lambda jid=jid: jobs.get_job(jid)["status"] == "cancelled"))
        finally:
            yandex_search._search_one_page_real = orig


class TestCancelSiteSearchJob(IsolatedStorageTestCase):
    """Отмена для раздела «Поиск по сайтам»."""

    def test_cancel_stops_site_search_job(self):
        from backend import site_search

        def slow_search(site, query):
            time.sleep(0.1)
            return []

        orig = site_search.search_one_site
        site_search.search_one_site = slow_search
        try:
            sites = [{"id": f"s{i}", "name": f"Сайт {i}", "url_template": f"https://s{i}.test"} for i in range(50)]
            job_id = jobs.start_site_search_job(sites, ["запрос"])
            self.assertTrue(_wait_until(lambda: jobs.get_site_search_job(job_id)["status"] == "running"))

            jobs.cancel_site_search_job(job_id)

            self.assertTrue(_wait_until(
                lambda: jobs.get_site_search_job(job_id)["status"] in ("cancelled", "done", "error")
            ))
            self.assertEqual(jobs.get_site_search_job(job_id)["status"], "cancelled")
        finally:
            site_search.search_one_site = orig

    def test_cancel_unknown_site_job_returns_none(self):
        self.assertIsNone(jobs.cancel_site_search_job("несуществующий-id"))


class TestCheckCaseNow(IsolatedStorageTestCase):
    """Ручная проверка доступности ссылки по кнопке — не зависит от
    фонового часового цикла."""

    def test_updates_case_with_status_and_timestamp(self):
        from unittest.mock import patch, MagicMock
        from backend import storage

        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        with patch("requests.get", return_value=MagicMock(status_code=200)):
            updated = jobs.check_case_now(case["id"])
        self.assertEqual(updated["link_status"], "доступна")
        self.assertGreater(updated["link_checked_at"], 0)

    def test_unknown_case_returns_none(self):
        self.assertIsNone(jobs.check_case_now("несуществующий-id"))


class TestCheckDueCasesOnce(IsolatedStorageTestCase):
    """Сам цикл фонового наблюдателя (_check_due_cases_once) — раньше был
    протестирован только по кусочкам (is_due, check, build_update_patch
    отдельно), а баг («автоматическая проверка ничего не пишет в журнал»)
    сидел именно на стыке, в этой функции. Эти тесты специально проверяют
    её целиком, включая журнал."""

    def _days_ago(self, days):
        return time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))

    def test_writes_to_audit_log(self):
        from unittest.mock import patch, MagicMock
        from backend import storage

        case = storage.add_blocking_case({
            "title": "т", "url": "https://x.test/1", "author_name": "А",
            "petition_filed_at": self._days_ago(20),
        })
        before = len(storage.load_audit_log(1000))
        with patch("requests.get", return_value=MagicMock(status_code=200)):
            jobs._check_due_cases_once()
        after = storage.load_audit_log(1000)
        self.assertGreater(len(after), before)
        self.assertIn("проверка доступности ссылки", after[0]["action"])
        self.assertTrue(after[0]["username"])  # не пусто — раньше баг был именно в этом

    def test_updates_the_actual_case_in_storage(self):
        from unittest.mock import patch, MagicMock
        from backend import storage

        case = storage.add_blocking_case({
            "title": "т", "url": "https://x.test/1", "author_name": "А",
            "petition_filed_at": self._days_ago(20),
        })
        with patch("requests.get", return_value=MagicMock(status_code=200)):
            jobs._check_due_cases_once()
        updated = storage.get_blocking_case(case["id"])
        self.assertEqual(updated["link_status"], "доступна")
        self.assertTrue(updated["needs_resend"])

    def test_skips_cases_that_are_not_due(self):
        from unittest.mock import patch, MagicMock
        from backend import storage

        case = storage.add_blocking_case({
            "title": "т", "url": "https://x.test/1", "author_name": "А",
            "petition_filed_at": self._days_ago(2),  # рано, не 14 дней
        })
        before = len(storage.load_audit_log(1000))
        with patch("requests.get", return_value=MagicMock(status_code=200)) as mock_get:
            jobs._check_due_cases_once()
        self.assertEqual(mock_get.call_count, 0)  # даже не попытались проверить
        self.assertEqual(len(storage.load_audit_log(1000)), before)

    def test_processes_multiple_due_cases_independently(self):
        from unittest.mock import patch, MagicMock
        from backend import storage

        storage.add_blocking_case({"title": "1", "url": "https://x.test/a", "author_name": "А", "petition_filed_at": self._days_ago(20)})
        storage.add_blocking_case({"title": "2", "url": "https://x.test/b", "author_name": "А", "petition_filed_at": self._days_ago(20)})
        with patch("requests.get", return_value=MagicMock(status_code=200)) as mock_get:
            jobs._check_due_cases_once()
        self.assertEqual(mock_get.call_count, 2)


class TestSiteSearchDedupeAndFilters(IsolatedStorageTestCase):
    """Регрессия на пункт из анализа реальных выдач. Уточнение по ходу
    написания этих тестов: search_sites() сама уже дедуплицирует
    результаты по ссылке (это было всегда, не баг) — реальным пробелом
    были стоп-слова (не с чем было отсеять однофамильные ложные
    срабатывания) и сверка с уже добавленными в блокировку ссылками."""

    def _run_and_wait(self, sites, queries, negative_keywords=None):
        job_id = jobs.start_site_search_job(sites, queries, negative_keywords)
        self.assertTrue(_wait_until(lambda: jobs.get_site_search_job(job_id)["status"] == "done"))
        return jobs.get_site_search_job(job_id)["result"]

    def test_negative_keywords_filter_out_homonym_false_positives(self):
        from backend import site_search

        def fake_search(site, query):
            return [
                {"url": "https://x.test/course-belousova", "title": "Курс Белоусова", "description": "курс графика"},
                {"url": "https://x.test/song-belousova", "title": "Песня Белоусова", "description": "скачать mp3 320 kbps"},
            ]

        orig = site_search.search_one_site
        site_search.search_one_site = fake_search
        try:
            sites = [{"id": "s1", "name": "Сайт 1", "url_template": "https://s1.test"}]
            result = self._run_and_wait(sites, ["Белоусова"], negative_keywords=["mp3", "kbps"])
        finally:
            site_search.search_one_site = orig

        urls = [r["url"] for r in result["results"]]
        self.assertIn("https://x.test/course-belousova", urls)
        self.assertNotIn("https://x.test/song-belousova", urls)

    def test_without_negative_keywords_nothing_is_filtered_by_words(self):
        from backend import site_search

        def fake_search(site, query):
            return [{"url": "https://x.test/1", "title": "т", "description": "что угодно"}]

        orig = site_search.search_one_site
        site_search.search_one_site = fake_search
        try:
            sites = [{"id": "s1", "name": "Сайт 1", "url_template": "https://s1.test"}]
            result = self._run_and_wait(sites, ["запрос"])
        finally:
            site_search.search_one_site = orig

        self.assertEqual(len(result["results"]), 1)

    def test_flags_results_already_in_blocking_table(self):
        from backend import site_search, storage

        storage.add_blocking_case({"title": "т", "url": "https://x.test/already", "author_name": "А"})

        def fake_search(site, query):
            return [
                {"url": "https://x.test/already", "title": "т", "description": ""},
                {"url": "https://x.test/new", "title": "т", "description": ""},
            ]

        orig = site_search.search_one_site
        site_search.search_one_site = fake_search
        try:
            sites = [{"id": "s1", "name": "Сайт 1", "url_template": "https://s1.test"}]
            result = self._run_and_wait(sites, ["запрос"])
        finally:
            site_search.search_one_site = orig

        by_url = {r["url"]: r for r in result["results"]}
        self.assertTrue(by_url["https://x.test/already"]["already_in_blocking"])
        self.assertFalse(by_url["https://x.test/new"]["already_in_blocking"])

    def test_site_search_itself_already_dedupes_by_url(self):
        """Не регрессия, а документирующий тест: фиксирует существующее
        (и всегда существовавшее) поведение search_sites(), чтобы будущая
        правка случайно его не сломала."""
        from backend import site_search

        def fake_search(site, query):
            return [{"url": "https://x.test/same", "title": "т", "description": ""}]

        orig = site_search.search_one_site
        site_search.search_one_site = fake_search
        try:
            sites = [
                {"id": "s1", "name": "Сайт 1", "url_template": "https://s1.test"},
                {"id": "s2", "name": "Сайт 2", "url_template": "https://s2.test"},
            ]
            result = self._run_and_wait(sites, ["запрос"])
        finally:
            site_search.search_one_site = orig

        self.assertEqual(len(result["results"]), 1)


if __name__ == "__main__":
    unittest.main()
