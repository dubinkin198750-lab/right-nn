import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import search_sources  # noqa: E402


def setUpModule():
    global _orig_inter_task_delay
    _orig_inter_task_delay = search_sources.INTER_TASK_DELAY_SEC
    search_sources.INTER_TASK_DELAY_SEC = 0  # не ждать реально в тестах


def tearDownModule():
    search_sources.INTER_TASK_DELAY_SEC = _orig_inter_task_delay


def item(url="", title="", description=""):
    return {"url": url, "title": title, "description": description, "position": 1}


class TestSignificantWords(unittest.TestCase):
    def test_strips_site_operator(self):
        words = search_sources._significant_words('+"Grammar mama" Белоусова site:avito.ru')
        self.assertNotIn("site", words)
        self.assertNotIn("avito", words)

    def test_strips_quotes_and_plus(self):
        words = search_sources._significant_words('+"Grammar mama" Белоусова')
        self.assertIn("grammar", words)
        self.assertIn("mama", words)
        self.assertIn("белоусова", words)

    def test_drops_short_words(self):
        words = search_sources._significant_words("я и он курс")
        self.assertNotIn("я", words)
        self.assertNotIn("и", words)
        self.assertIn("курс", words)


class TestLooksRelevant(unittest.TestCase):
    """Регрессия на реальный кейс: поиск по Avito для курса Grammar Mama
    (Белоусова) возвращал категорийные страницы про мотоциклы, стройматериалы
    и т.п. — совершенно не связанные с запросом."""

    def setUp(self):
        self.words = search_sources._significant_words('+"Grammar mama" Белоусова')

    def test_unrelated_category_page_rejected(self):
        garbage = item(
            url="https://www.avito.ru/all/mototsikly_i_mototehnika?q=honda+africa+twin",
            description="420 объявлений о продаже мотоциклов и мототехники во всех регионах на Авито.",
        )
        self.assertFalse(search_sources._looks_relevant(garbage, self.words))

    def test_another_unrelated_category_rejected(self):
        garbage = item(
            url="https://www.avito.ru/all/dlya_doma_i_dachi?q=%D0%B1%D0%B0%D0%BA%D0%BB%D0%B0%D0%B6%D0%BA%D0%B8",
            description="Кондиционеры и вентиляция, стиральные машины, стройматериалы...",
        )
        self.assertFalse(search_sources._looks_relevant(garbage, self.words))

    def test_relevant_grammar_book_kept(self):
        relevant = item(
            url="https://www.avito.ru/moskva/knigi_i_zhurnaly?q=essential+grammar+in+use",
            description="Продам учебник Essential Grammar in Use.",
        )
        self.assertTrue(search_sources._looks_relevant(relevant, self.words))

    def test_relevant_by_author_name_kept(self):
        relevant = item(
            url="https://www.avito.ru/moskva/knigi_i_zhurnaly?q=belousova",
            description="Курс Белоусовой по грамматике, диск с материалами.",
        )
        self.assertTrue(search_sources._looks_relevant(relevant, self.words))

    def test_no_significant_words_keeps_everything(self):
        self.assertTrue(search_sources._looks_relevant(item(), []))


class TestRunSearchFiltersAvito(unittest.TestCase):
    """Интеграционный тест на весь путь run_search в демо-режиме — без
    настоящих ключей API, но с подменой поисковой функции, чтобы проверить,
    что нерелевантные avito-результаты реально отсекаются на выходе."""

    def test_irrelevant_avito_items_filtered_out_of_final_results(self):
        import backend.yandex_search as ys

        original_search = ys.search

        def fake_search(query_text, pages, progress_cb=None, should_stop=None):
            if "site:avito.ru" in query_text:
                return [
                    item(url="https://avito.ru/x1", description="курс Grammar mama Белоусовой скидка"),
                    item(url="https://avito.ru/motocycles", description="420 объявлений о продаже мотоциклов"),
                ], False
            return [item(url="https://example.com/x2", title="что-то из обычного поиска")], False

        ys.search = fake_search
        try:
            items, demo = search_sources.run_search(
                '+"Grammar mama" Белоусова', 5,
                {"yandex": True, "google": False, "avito": True, "telegram": False},
            )
            urls = [it["url"] for it in items]
            self.assertIn("https://avito.ru/x1", urls)
            self.assertNotIn("https://avito.ru/motocycles", urls)
            self.assertIn("https://example.com/x2", urls)  # обычный поиск не фильтруется этой проверкой
        finally:
            ys.search = original_search


class TestBuildTasksMultiQuery(unittest.TestCase):
    """Регрессия/новая функциональность: у произведения теперь можно задать
    несколько вариантов формулировки запроса (список), не только одну строку
    (старый формат)."""

    def test_single_string_query_backward_compatible(self):
        tasks = search_sources.build_tasks("курс Иванова", {"yandex": True, "google": False, "avito": False, "telegram": False})
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0][1], "курс Иванова")

    def test_list_of_queries_produces_task_per_query_per_source(self):
        tasks = search_sources.build_tasks(
            ["курс Иванова скачать", "курс Иванова складчина"],
            {"yandex": True, "google": True, "avito": False, "telegram": False},
        )
        self.assertEqual(len(tasks), 4)  # 2 запроса × 2 источника
        query_texts = {t[1] for t in tasks}
        self.assertEqual(query_texts, {"курс Иванова скачать", "курс Иванова складчина"})

    def test_empty_strings_in_list_are_dropped(self):
        tasks = search_sources.build_tasks(
            ["курс Иванова", "  ", ""],
            {"yandex": True, "google": False, "avito": False, "telegram": False},
        )
        self.assertEqual(len(tasks), 1)

    def test_avito_site_filter_applied_per_query(self):
        tasks = search_sources.build_tasks(
            ["запрос1", "запрос2"],
            {"yandex": True, "google": False, "avito": True, "telegram": False},
        )
        avito_tasks = [t for t in tasks if t[2] == search_sources.SOURCE_LABELS["avito"]]
        self.assertEqual(len(avito_tasks), 2)
        self.assertTrue(all("site:avito.ru" in t[1] for t in avito_tasks))


class TestRunSearchMultiQueryDedup(unittest.TestCase):
    """Одна и та же ссылка, найденная разными вариантами запроса, должна
    засчитываться один раз, а не дублироваться в итоговом списке."""

    def test_same_url_from_different_queries_deduplicated(self):
        import backend.yandex_search as ys
        original_search = ys.search

        def fake_search(query_text, pages, progress_cb=None, should_stop=None):
            return [item(url="https://pirate.test/same-course", title=f"найдено по «{query_text}»")], False

        ys.search = fake_search
        try:
            items, demo = search_sources.run_search(
                ["курс Иванова скачать", "курс Иванова складчина"], 5,
                {"yandex": True, "google": False, "avito": False, "telegram": False},
            )
            self.assertEqual(len(items), 1)  # не задвоилось
        finally:
            ys.search = original_search

    def test_different_urls_from_different_queries_both_kept(self):
        import backend.yandex_search as ys
        original_search = ys.search

        def fake_search(query_text, pages, progress_cb=None, should_stop=None):
            return [item(url=f"https://pirate.test/{query_text}", title=query_text)], False

        ys.search = fake_search
        try:
            items, demo = search_sources.run_search(
                ["a", "b"], 5, {"yandex": True, "google": False, "avito": False, "telegram": False},
            )
            self.assertEqual(len(items), 2)
        finally:
            ys.search = original_search


class TestRunSearchTaskFailureResilience(unittest.TestCase):
    """Регрессия: если у одного из нескольких вариантов запроса (или
    источников) поиск целиком упал (например, все страницы этого запроса не
    ответили вовремя) — результаты уже успешно пройденных запросов/источников
    не должны теряться."""

    def test_one_failing_query_does_not_lose_results_from_others(self):
        import backend.yandex_search as ys
        original_search = ys.search

        def fake_search(query_text, pages, progress_cb=None, should_stop=None):
            if query_text == "плохой запрос":
                raise ys.YandexSearchError("Превышено время ожидания ответа Yandex Search API (страница 7)")
            return [item(url=f"https://pirate.test/{query_text}", title=query_text)], False

        ys.search = fake_search
        try:
            items, demo = search_sources.run_search(
                ["хороший запрос", "плохой запрос"], 5,
                {"yandex": True, "google": False, "avito": False, "telegram": False},
            )
            self.assertEqual(len(items), 1)  # результат хорошего запроса не потерян
            self.assertEqual(items[0]["url"], "https://pirate.test/хороший запрос")
        finally:
            ys.search = original_search

    def test_result_found_before_empty_but_successful_task_not_treated_as_failure(self):
        """Регрессия на конкретную найденную неточность: 'нет результатов'
        (запрос отработал, но ничего не нашёл) и 'запрос вообще не выполнился'
        — разные вещи, их нельзя путать через простую проверку 'пусто ли'."""
        import backend.yandex_search as ys
        original_search = ys.search

        def fake_search(query_text, pages, progress_cb=None, should_stop=None):
            if query_text == "пустой запрос":
                return [], False  # успешно, но ничего не нашёл
            if query_text == "плохой запрос":
                raise ys.YandexSearchError("сбой")
            return [], False

        ys.search = fake_search
        try:
            # не должно поднять исключение, хотя итоговый список пуст —
            # часть задач реально успешно отработала (просто без находок)
            items, demo = search_sources.run_search(
                ["пустой запрос", "плохой запрос"], 5,
                {"yandex": True, "google": False, "avito": False, "telegram": False},
            )
            self.assertEqual(items, [])
        finally:
            ys.search = original_search

    def test_all_tasks_failing_raises_error(self):
        import backend.yandex_search as ys
        original_search = ys.search

        def always_fails(query_text, pages, progress_cb=None, should_stop=None):
            raise ys.YandexSearchError("сбой")

        ys.search = always_fails
        try:
            with self.assertRaises(ys.YandexSearchError):
                search_sources.run_search(
                    "запрос", 5, {"yandex": True, "google": False, "avito": False, "telegram": False},
                )
        finally:
            ys.search = original_search


class TestDuckDuckGoIntegration(unittest.TestCase):
    """DuckDuckGo — третий источник наряду с Yandex/Google, встроен по
    тому же принципу (тот же build_tasks/run_search диспетчер)."""

    def test_duckduckgo_enabled_adds_task(self):
        tasks = search_sources.build_tasks(
            "курс Иванова",
            {"yandex": False, "google": False, "duckduckgo": True, "avito": False, "telegram": False},
        )
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0][0], "duckduckgo")
        self.assertEqual(tasks[0][2], "DuckDuckGo")

    def test_all_three_engines_together(self):
        tasks = search_sources.build_tasks(
            "запрос",
            {"yandex": True, "google": True, "duckduckgo": True, "avito": False, "telegram": False},
        )
        self.assertEqual(len(tasks), 3)
        engines = {t[0] for t in tasks}
        self.assertEqual(engines, {"yandex", "google", "duckduckgo"})

    def test_duckduckgo_used_for_avito_site_filter_when_selected(self):
        tasks = search_sources.build_tasks(
            "запрос",
            {"yandex": False, "google": False, "duckduckgo": True, "avito": True, "telegram": False},
        )
        avito_tasks = [t for t in tasks if t[2] == search_sources.SOURCE_LABELS["avito"]]
        self.assertEqual(len(avito_tasks), 1)
        self.assertEqual(avito_tasks[0][0], "duckduckgo")

    def test_run_search_dispatches_to_duckduckgo_module(self):
        import backend.duckduckgo_search as ddg
        original_search = ddg.search

        def fake_search(query_text, pages, progress_cb=None, should_stop=None):
            return [{"title": "т", "url": "https://x.test/1", "description": ""}], False

        ddg.search = fake_search
        try:
            items, demo = search_sources.run_search(
                "запрос", 1, {"yandex": False, "google": False, "duckduckgo": True, "avito": False, "telegram": False},
            )
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["source"], "DuckDuckGo")
        finally:
            ddg.search = original_search

    def test_is_duckduckgo_configured_always_true(self):
        self.assertTrue(search_sources.is_duckduckgo_configured())


if __name__ == "__main__":
    unittest.main()
