"""Тесты для backend/filters.py — запускаются встроенным unittest, без
дополнительных пакетов: `python3 -m unittest discover tests` из корня проекта.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import filters  # noqa: E402


def item(url, title="", description=""):
    return {"url": url, "title": title, "description": description, "position": 1, "source": "Тест"}


class TestExcludeBlockedDomains(unittest.TestCase):
    def test_excludes_matching_domain(self):
        items = [item("https://official-site.ru/page"), item("https://pirate.biz/thread/1")]
        result = filters.exclude_blocked_domains(items, ["official-site.ru"])
        self.assertEqual([r["url"] for r in result], ["https://pirate.biz/thread/1"])

    def test_case_insensitive(self):
        items = [item("https://OFFICIAL-SITE.ru/page")]
        result = filters.exclude_blocked_domains(items, ["official-site.ru"])
        self.assertEqual(result, [])

    def test_empty_blocklist_keeps_everything(self):
        items = [item("https://a.test"), item("https://b.test")]
        result = filters.exclude_blocked_domains(items, [])
        self.assertEqual(len(result), 2)


class TestFilterByKeywords(unittest.TestCase):
    def test_no_keywords_keeps_everything(self):
        items = [item("https://a.test", description="что угодно")]
        result = filters.filter_by_keywords(items, [])
        self.assertEqual(len(result), 1)

    def test_exact_phrase_match(self):
        items = [
            item("https://a.test", description="курс Иванова про нейросети"),
            item("https://b.test", description="ничего похожего"),
        ]
        result = filters.filter_by_keywords(items, ["курс Иванова"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["url"], "https://a.test")

    def test_and_group_via_comma_requires_all_words(self):
        items = [
            item("https://a.test", description="иванов курс складчина скачать"),
            item("https://b.test", description="иванов книга про кулинарию"),  # только "иванов", без "складчина"
        ]
        result = filters.filter_by_keywords(items, ["иванов, складчина"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["url"], "https://a.test")

    def test_and_group_words_in_any_order(self):
        items = [item("https://a.test", description="складчина курс от Иванова здесь")]
        result = filters.filter_by_keywords(items, ["иванова, складчина"])
        self.assertEqual(len(result), 1)

    def test_multiple_rules_are_or(self):
        items = [
            item("https://a.test", description="первое совпадение"),
            item("https://b.test", description="второе совпадение"),
            item("https://c.test", description="мимо"),
        ]
        result = filters.filter_by_keywords(items, ["первое", "второе"])
        self.assertEqual(len(result), 2)

    def test_matches_url_too_not_only_description(self):
        items = [item("https://a.test/threads/ivanov-kurs.123/", description="")]
        result = filters.filter_by_keywords(items, ["ivanov"])
        self.assertEqual(len(result), 1)


class TestNegativeKeywords(unittest.TestCase):
    """Стоп-слова реализованы как третий параметр filter_by_keywords,
    отдельной функции exclude_by_negative_keywords в модуле нет."""

    def test_negative_keyword_removes_match(self):
        items = [
            item("https://a.test", description="курс книга Андрианова fb2 скачать"),
            item("https://b.test", description="курс Андрианова складчина"),
        ]
        result = filters.filter_by_keywords(items, [], negative_keywords=["fb2", "книга"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["url"], "https://b.test")

    def test_negative_keyword_wins_even_if_positive_matches(self):
        items = [item("https://a.test", description="иванов складчина книга")]
        result = filters.filter_by_keywords(items, ["иванов, складчина"], negative_keywords=["книга"])
        self.assertEqual(result, [])  # стоп-слово отбрасывает, даже если позитивное правило совпало

    def test_no_negative_keywords_keeps_everything(self):
        items = [item("https://a.test", description="что угодно")]
        result = filters.filter_by_keywords(items, [], negative_keywords=[])
        self.assertEqual(len(result), 1)


class TestDedupeByUrl(unittest.TestCase):
    def test_removes_duplicate_urls_keeps_first(self):
        items = [
            item("https://a.test", title="первый"),
            item("https://a.test", title="дубль"),
            item("https://b.test", title="другой"),
        ]
        result = filters.dedupe_by_url(items)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["title"], "первый")


class TestRunPipeline(unittest.TestCase):
    def test_full_pipeline_order_of_operations(self):
        raw = [
            item("https://official.test/x", description="иванов курс"),  # уберётся блок-листом
            item("https://pirate.test/1", description="иванов курс складчина"),
            item("https://pirate.test/1", description="дубликат по url"),
            item("https://pirate.test/2", description="ничего общего с запросом"),
        ]
        pipeline = filters.run_pipeline(raw, ["иванов, складчина"], ["official.test"], [])
        self.assertEqual(pipeline["raw_count"], 4)
        self.assertEqual(pipeline["after_domain_exclude"], 3)
        self.assertEqual(pipeline["after_keyword_filter"], 1)
        self.assertEqual(pipeline["after_dedupe"], 1)
        self.assertEqual(pipeline["results"][0]["url"], "https://pirate.test/1")

    def test_fallback_all_results_present_when_filter_matches_nothing(self):
        raw = [item("https://a.test", description="совсем не то")]
        pipeline = filters.run_pipeline(raw, ["слово_которого_тут_нет"], [], [])
        self.assertEqual(pipeline["after_keyword_filter"], 0)
        self.assertEqual(len(pipeline["all_results"]), 1)  # доступно для отката на «показать всё»


if __name__ == "__main__":
    unittest.main()
