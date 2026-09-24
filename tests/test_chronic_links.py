"""Тесты backend/chronic_links.py — «Постоянно блокируемые ссылки».
Раньше у этого модуля не было тестов вообще, несмотря на то, что от него
зависит реальное поведение (какие дела исчезают из «Блокировки» и
показываются в отдельном разделе, кому автоматически снимают скриншоты)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage, chronic_links  # noqa: E402


class TestBaseDomain(unittest.TestCase):
    """_base_domain — чистая функция, без обращения к storage, тестируется
    без изоляции файловой системы."""

    def test_subdomain_collapses_to_base_domain(self):
        self.assertEqual(chronic_links._base_domain("s69.zapret.me"), "zapret.me")
        self.assertEqual(chronic_links._base_domain("s68.zapret.me"), "zapret.me")

    def test_bare_domain_unchanged(self):
        self.assertEqual(chronic_links._base_domain("zapret.me"), "zapret.me")

    def test_multi_part_tld_keeps_three_labels(self):
        """example.co.uk — "co.uk" сама по себе не домен, а составная
        зона, наивное "последние 2 части" дало бы неверный результат."""
        self.assertEqual(chronic_links._base_domain("shop.example.co.uk"), "example.co.uk")
        self.assertEqual(chronic_links._base_domain("example.co.uk"), "example.co.uk")

    def test_empty_input(self):
        self.assertEqual(chronic_links._base_domain(""), "")
        self.assertEqual(chronic_links._base_domain(None), "")


class TestCountDomainOccurrences(IsolatedStorageTestCase):
    def test_below_threshold_not_chronic(self):
        storage.add_blocking_case({
            "title": "т", "url": "https://s69.zapret.me/threads/x/", "author_name": "Автор", "work_title": "Курс",
        })
        count, domain = chronic_links.count_domain_occurrences("Автор", "Курс", "https://s69.zapret.me/threads/x/")
        self.assertEqual(count, 1)
        self.assertEqual(domain, "zapret.me")
        self.assertLess(count, chronic_links.CHRONIC_THRESHOLD)

    def test_different_subdomain_same_base_domain_counts_together(self):
        """Ровно тот сценарий, ради которого фича и делалась: s69/s68 —
        разные поддомены, один и тот же сайт-зеркало, ОДИН и тот же курс."""
        storage.add_blocking_case({"title": "т", "url": "https://s69.zapret.me/threads/x/", "author_name": "Автор", "work_title": "Курс"})
        storage.add_blocking_case({"title": "т", "url": "https://s68.zapret.me/threads/x/", "author_name": "Автор", "work_title": "Курс"})
        count, domain = chronic_links.count_domain_occurrences("Автор", "Курс", "https://s68.zapret.me/threads/x/")
        self.assertEqual(count, 2)
        self.assertEqual(domain, "zapret.me")
        self.assertGreaterEqual(count, chronic_links.CHRONIC_THRESHOLD)

    def test_different_author_same_domain_counts_separately(self):
        """Домен общий, но авторы разные — не должны смешиваться в один счётчик."""
        storage.add_blocking_case({"title": "т", "url": "https://zapret.me/a", "author_name": "Автор А", "work_title": "Курс"})
        storage.add_blocking_case({"title": "т", "url": "https://zapret.me/b", "author_name": "Автор Б", "work_title": "Курс"})
        count_a, _ = chronic_links.count_domain_occurrences("Автор А", "Курс", "https://zapret.me/a")
        count_b, _ = chronic_links.count_domain_occurrences("Автор Б", "Курс", "https://zapret.me/b")
        self.assertEqual(count_a, 1)
        self.assertEqual(count_b, 1)

    def test_different_work_same_author_and_domain_counts_separately(self):
        """Ключевой сценарий из обсуждения 03.09: два РАЗНЫХ произведения
        одного автора на одной большой площадке (VK, форум-агрегатор
        вроде skladchinmore.cc) — это не «зеркало», не должны
        объединяться в один счётчик, даже если домен и автор совпадают."""
        storage.add_blocking_case({"title": "т", "url": "https://big-platform.test/a", "author_name": "Автор", "work_title": "Курс А"})
        storage.add_blocking_case({"title": "т", "url": "https://big-platform.test/b", "author_name": "Автор", "work_title": "Курс Б"})
        count_a, _ = chronic_links.count_domain_occurrences("Автор", "Курс А", "https://big-platform.test/a")
        count_b, _ = chronic_links.count_domain_occurrences("Автор", "Курс Б", "https://big-platform.test/b")
        self.assertEqual(count_a, 1)
        self.assertEqual(count_b, 1)

    def test_url_without_valid_host_returns_zero(self):
        count, domain = chronic_links.count_domain_occurrences("Автор", "Курс", "")
        self.assertEqual(count, 0)
        self.assertEqual(domain, "")


class TestComputeChronicDomains(IsolatedStorageTestCase):
    def test_group_appears_only_at_threshold(self):
        storage.add_blocking_case({"title": "т", "url": "https://s69.zapret.me/x", "author_name": "Автор", "work_title": "Курс"})
        self.assertEqual(chronic_links.compute_chronic_domains(), [])  # 1 повтор — ещё не хронический

        storage.add_blocking_case({"title": "т", "url": "https://s68.zapret.me/x", "author_name": "Автор", "work_title": "Курс"})
        groups = chronic_links.compute_chronic_domains()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["author_name"], "Автор")
        self.assertEqual(groups[0]["work_title"], "Курс")
        self.assertEqual(groups[0]["base_domain"], "zapret.me")
        self.assertEqual(groups[0]["count"], 2)
        self.assertEqual(len(groups[0]["active_case_ids"]), 2)
        self.assertEqual(groups[0]["archived_count"], 0)

    def test_different_works_on_same_big_platform_not_grouped(self):
        """Тот самый реальный пример из обсуждения: два разных тарифа
        одного курса — если это буквально РАЗНЫЕ произведения в системе
        (разные work_title) — не считаются одной хронической группой."""
        storage.add_blocking_case({"title": "т", "url": "https://skladchinmore.test/klon-imperija", "author_name": "Андрианов", "work_title": "Тариф Империя"})
        storage.add_blocking_case({"title": "т", "url": "https://skladchinmore.test/klon-sistema", "author_name": "Андрианов", "work_title": "Тариф Система"})
        self.assertEqual(chronic_links.compute_chronic_domains(), [])

    def test_archived_cases_count_toward_threshold_but_not_active_ids(self):
        """Заархивированные (завершённые месяцы) дела учитываются в счётчике
        повторов, но не попадают в active_case_ids — для них нет интерфейса
        для действий (заявление/скриншоты), это просто исторический факт."""
        storage.add_blocking_case({"title": "т", "url": "https://s69.zapret.me/x", "author_name": "Автор", "work_title": "Курс"})
        storage.save_report_archive([
            {"id": "archived-1", "title": "т", "url": "https://s68.zapret.me/x", "author_name": "Автор", "work_title": "Курс", "added_at": time.time() - 100000},
        ])
        groups = chronic_links.compute_chronic_domains()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["count"], 2)
        self.assertEqual(len(groups[0]["active_case_ids"]), 1)  # только активное
        self.assertEqual(groups[0]["archived_count"], 1)

    def test_groups_sorted_by_count_descending(self):
        # Автор Б — 3 повтора одного домена
        for i in range(3):
            storage.add_blocking_case({"title": "т", "url": f"https://s{i}.big.me/x", "author_name": "Автор Б", "work_title": "Курс"})
        # Автор А — 2 повтора
        storage.add_blocking_case({"title": "т", "url": "https://s1.small.me/x", "author_name": "Автор А", "work_title": "Курс"})
        storage.add_blocking_case({"title": "т", "url": "https://s2.small.me/x", "author_name": "Автор А", "work_title": "Курс"})

        groups = chronic_links.compute_chronic_domains()
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["author_name"], "Автор Б")  # 3 повтора — первый
        self.assertEqual(groups[0]["count"], 3)
        self.assertEqual(groups[1]["author_name"], "Автор А")  # 2 повтора — второй
        self.assertEqual(groups[1]["count"], 2)

    def test_unrelated_single_case_not_included(self):
        """Одна-единственная ссылка на своём домене — обычное дело
        блокировки, не должна попадать в «постоянно блокируемые»."""
        storage.add_blocking_case({"title": "т", "url": "https://onesite.example/x", "author_name": "Автор", "work_title": "Курс"})
        self.assertEqual(chronic_links.compute_chronic_domains(), [])


class TestChronicActiveCaseIds(IsolatedStorageTestCase):
    def test_returns_ids_from_all_qualifying_groups(self):
        c1 = storage.add_blocking_case({"title": "т", "url": "https://s1.a.me/x", "author_name": "Автор А", "work_title": "Курс"})
        c2 = storage.add_blocking_case({"title": "т", "url": "https://s2.a.me/x", "author_name": "Автор А", "work_title": "Курс"})
        c3 = storage.add_blocking_case({"title": "т", "url": "https://onesite.example/x", "author_name": "Автор Б", "work_title": "Курс"})

        ids = chronic_links.chronic_active_case_ids()
        self.assertEqual(ids, {c1["id"], c2["id"]})
        self.assertNotIn(c3["id"], ids)  # одиночная ссылка — не хроническая


class TestChronicDomainsEndpoint(IsolatedStorageTestCase):
    """Проверка на уровне HTTP — /api/chronic-domains и то, что
    /api/blocking-cases по-прежнему отдаёт ВСЕ дела без фильтрации
    (фильтрация «хронических» из обычной «Блокировки» — сознательно
    решение фронтенда, не бэкенда, см. app.js renderBlockingTable)."""

    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def test_endpoint_returns_qualifying_groups(self):
        storage.add_blocking_case({"title": "т", "url": "https://s1.a.me/x", "author_name": "Автор", "work_title": "Курс"})
        storage.add_blocking_case({"title": "т", "url": "https://s2.a.me/x", "author_name": "Автор", "work_title": "Курс"})
        resp = self.client.get("/api/chronic-domains")
        self.assertEqual(resp.status_code, 200)
        groups = resp.get_json()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["base_domain"], "a.me")

    def test_blocking_cases_endpoint_not_filtered_server_side(self):
        """Важно: /api/blocking-cases отдаёт и хронические дела тоже —
        фильтрация происходит только в браузере (см. app.js), чтобы
        остальные потребители API (CSV-экспорт, подготовка заявления и
        т.п.) продолжали видеть полный список без исключений."""
        storage.add_blocking_case({"title": "т", "url": "https://s1.a.me/x", "author_name": "Автор", "work_title": "Курс"})
        storage.add_blocking_case({"title": "т", "url": "https://s2.a.me/x", "author_name": "Автор", "work_title": "Курс"})
        resp = self.client.get("/api/blocking-cases")
        self.assertEqual(len(resp.get_json()), 2)


if __name__ == "__main__":
    unittest.main()
