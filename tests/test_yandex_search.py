import os
import sys
import time
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import yandex_search  # noqa: E402


class TestBuildRequestBody(unittest.TestCase):
    def test_family_mode_is_explicitly_disabled(self):
        """Регрессия: без явного FAMILY_MODE_NONE API мог применять
        собственный фильтр контента по умолчанию, из-за чего часть
        результатов (в т.ч. пиратские копии) не попадала в выдачу."""
        body = yandex_search._build_request_body("тестовый запрос", 0)
        self.assertEqual(body["query"]["familyMode"], "FAMILY_MODE_NONE")

    def test_query_text_and_page_passed_through(self):
        body = yandex_search._build_request_body("курс Иванова", 3)
        self.assertEqual(body["query"]["queryText"], "курс Иванова")
        self.assertEqual(body["query"]["page"], 3)

    def test_folder_id_from_environment(self):
        os.environ["YANDEX_FOLDER_ID"] = "b1gtest12345"
        try:
            body = yandex_search._build_request_body("запрос", 0)
            self.assertEqual(body["folderId"], "b1gtest12345")
        finally:
            os.environ.pop("YANDEX_FOLDER_ID", None)


class TestRetryOn429(unittest.TestCase):
    """Регрессия: массовый запуск многих произведений сразу («Искать по всем
    активным») может упереться в лимит запросов Yandex Search API (429) —
    без повторных попыток такие произведения просто падали бы с ошибкой."""

    def setUp(self):
        self._orig_retries = yandex_search.MAX_429_RETRIES
        yandex_search.MAX_429_RETRIES = 1  # чтобы тест не ждал реально долго

    def tearDown(self):
        yandex_search.MAX_429_RETRIES = self._orig_retries

    def test_succeeds_after_one_429(self):
        session = MagicMock()
        resp_429 = MagicMock(status_code=429, headers={})
        resp_ok = MagicMock(status_code=200)
        session.post.side_effect = [resp_429, resp_ok]

        result = yandex_search._post_with_retry(session, "http://x", {}, {}, 30)
        self.assertIs(result, resp_ok)
        self.assertEqual(session.post.call_count, 2)

    def test_raises_clear_error_after_exhausting_retries(self):
        session = MagicMock()
        resp_429 = MagicMock(status_code=429, headers={})
        session.post.return_value = resp_429

        with self.assertRaises(yandex_search.YandexSearchError) as ctx:
            yandex_search._post_with_retry(session, "http://x", {}, {}, 30)
        self.assertIn("429", str(ctx.exception))

    def test_non_429_error_status_raises_immediately_without_retry(self):
        import requests
        session = MagicMock()
        resp_500 = MagicMock(status_code=500)
        resp_500.raise_for_status.side_effect = requests.exceptions.HTTPError("500 error")
        session.post.return_value = resp_500

        with self.assertRaises(requests.exceptions.HTTPError):
            yandex_search._post_with_retry(session, "http://x", {}, {}, 30)
        self.assertEqual(session.post.call_count, 1)  # не повторяет для не-429 ошибок


class TestPageFailureResilience(unittest.TestCase):
    """Регрессия на реальный кейс: таймаут на одной странице (например,
    странице 7) не должен ронять результаты, уже успешно полученные с
    остальных страниц того же запроса."""

    def setUp(self):
        self._orig_delay = yandex_search.PAGE_DELAY_SEC
        yandex_search.PAGE_DELAY_SEC = 0  # не ждать реально в тестах
        os.environ["YANDEX_API_KEY"] = "test"
        os.environ["YANDEX_FOLDER_ID"] = "test"

    def tearDown(self):
        yandex_search.PAGE_DELAY_SEC = self._orig_delay
        os.environ.pop("YANDEX_API_KEY", None)
        os.environ.pop("YANDEX_FOLDER_ID", None)

    def test_one_failed_page_does_not_lose_results_from_other_pages(self):
        import backend.yandex_search as ys

        def fake_page(query_text, page, session):
            if page == 7:
                raise ys.YandexSearchError("Превышено время ожидания ответа Yandex Search API (страница 7)")
            return [{"url": f"https://x.test/{page}", "title": f"стр. {page}"}]

        orig = ys._search_one_page_real
        ys._search_one_page_real = fake_page
        try:
            results, demo = ys.search("тестовый запрос", 10)
            self.assertFalse(demo)
            self.assertEqual(len(results), 9)  # все, кроме упавшей 7-й
            urls = {r["url"] for r in results}
            self.assertNotIn("https://x.test/7", urls)
        finally:
            ys._search_one_page_real = orig

    def test_all_pages_failing_raises_error(self):
        import backend.yandex_search as ys

        def always_fails(query_text, page, session):
            raise ys.YandexSearchError("сбой")

        orig = ys._search_one_page_real
        ys._search_one_page_real = always_fails
        try:
            with self.assertRaises(ys.YandexSearchError):
                ys.search("тестовый запрос", 3)
        finally:
            ys._search_one_page_real = orig

    def test_progress_callback_still_fires_for_failed_page(self):
        import backend.yandex_search as ys

        def fake_page(query_text, page, session):
            if page == 2:
                raise ys.YandexSearchError("сбой")
            return []

        seen_pages = []

        def cb(page, total):
            seen_pages.append(page)

        orig = ys._search_one_page_real
        ys._search_one_page_real = fake_page
        try:
            ys.search("запрос", 3, progress_cb=cb)
            self.assertEqual(seen_pages, [1, 2, 3])  # прогресс идёт дальше, не застревает
        finally:
            ys._search_one_page_real = orig


class TestCancellation(unittest.TestCase):
    """Кнопка «Остановить поиск» — should_stop должен прерывать цикл по
    страницам, не дожидаясь конца всех запланированных страниц, и не
    считаться ошибкой (в отличие от таймаута/сбоя)."""

    def setUp(self):
        self._orig_delay = yandex_search.PAGE_DELAY_SEC
        yandex_search.PAGE_DELAY_SEC = 0
        os.environ["YANDEX_API_KEY"] = "test"
        os.environ["YANDEX_FOLDER_ID"] = "test"

    def tearDown(self):
        yandex_search.PAGE_DELAY_SEC = self._orig_delay
        os.environ.pop("YANDEX_API_KEY", None)
        os.environ.pop("YANDEX_FOLDER_ID", None)

    def test_stops_immediately_when_already_requested(self):
        import backend.yandex_search as ys
        calls = []

        def fake_page(query_text, page, session):
            calls.append(page)
            return [{"url": f"https://x.test/{page}", "title": "т"}]

        orig = ys._search_one_page_real
        ys._search_one_page_real = fake_page
        try:
            results, demo = ys.search("запрос", 5, should_stop=lambda: True)
            self.assertEqual(results, [])
            self.assertEqual(calls, [])  # ни одной страницы даже не попробовали
        finally:
            ys._search_one_page_real = orig

    def test_stops_partway_keeps_earlier_pages(self):
        import backend.yandex_search as ys

        def fake_page(query_text, page, session):
            return [{"url": f"https://x.test/{page}", "title": "т"}]

        stop_after = {"page": 0}

        def should_stop():
            return stop_after["page"] >= 2

        def fake_page_tracking(query_text, page, session):
            stop_after["page"] = page
            return fake_page(query_text, page, session)

        orig = ys._search_one_page_real
        ys._search_one_page_real = fake_page_tracking
        try:
            results, demo = ys.search("запрос", 5, should_stop=should_stop)
            urls = {r["url"] for r in results}
            self.assertIn("https://x.test/1", urls)
            self.assertIn("https://x.test/2", urls)
            self.assertNotIn("https://x.test/4", urls)
            self.assertNotIn("https://x.test/5", urls)
        finally:
            ys._search_one_page_real = orig

    def test_cancellation_not_treated_as_error(self):
        import backend.yandex_search as ys

        def fake_page(query_text, page, session):
            return [{"url": f"https://x.test/{page}", "title": "т"}]

        orig = ys._search_one_page_real
        ys._search_one_page_real = fake_page
        try:
            # не должно поднять исключение
            results, demo = ys.search("запрос", 3, should_stop=lambda: True)
        finally:
            ys._search_one_page_real = orig


if __name__ == "__main__":
    unittest.main()
