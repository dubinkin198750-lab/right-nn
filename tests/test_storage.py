"""Тесты для backend/storage.py. Каждый тест работает в изолированной
временной папке (не трогает вашу настоящую папку data/)."""
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import storage  # noqa: E402
from tests._helpers import IsolatedStorageTestCase as StorageTestCase  # noqa: E402


class TestAuthorsCrud(StorageTestCase):
    def test_create_and_get(self):
        a = storage.upsert_author({"id": None, "name": "Тестов Тест"})
        self.assertTrue(a["id"])
        fetched = storage.get_author(a["id"])
        self.assertEqual(fetched["name"], "Тестов Тест")

    def test_delete_author_cascades_to_works(self):
        a = storage.upsert_author({"id": None, "name": "Автор"})
        w = storage.upsert_work({"id": None, "author_id": a["id"], "title": "Курс",
                                  "query": "q", "keywords": [], "pages": 5})
        storage.delete_author(a["id"])
        self.assertIsNone(storage.get_author(a["id"]))
        self.assertIsNone(storage.get_work(w["id"]))

    def test_delete_author_cascades_to_documents_on_disk(self):
        """Документы теперь хранятся зашифрованными в document_vault, не в
        обычной DOCUMENTS_DIR — проверяем, что каскадное удаление автора
        подчищает файл именно в зашифрованном хранилище."""
        a = storage.upsert_author({"id": None, "name": "Автор с документом"})
        fname = "test_stored.pdf"
        storage.document_vault.save_encrypted(fname, b"fake pdf content")
        storage.add_document({
            "author_id": a["id"], "original_name": "doc.pdf", "stored_filename": fname,
            "doc_type": "доверенность", "description": "", "size": 10, "uploaded_at": 0,
        })
        vault_path = os.path.join(storage.document_vault._vault_dir(), fname)
        self.assertTrue(os.path.exists(vault_path))
        storage.delete_author(a["id"])
        self.assertFalse(os.path.exists(vault_path))
        self.assertEqual(storage.get_author_documents(a["id"]), [])


class TestBlockingCaseCrud(StorageTestCase):
    def test_default_fields_applied(self):
        c = storage.add_blocking_case({"url": "https://x.test/1", "title": "т"})
        self.assertEqual(c["claim_decision"], "")
        self.assertEqual(c["first_appeal_decision"], "")
        self.assertEqual(c["repeat_appeal_decision"], "")
        self.assertFalse(c["presence_google"])

    def test_update_patches_only_given_fields(self):
        c = storage.add_blocking_case({"url": "https://x.test/1", "title": "т"})
        storage.update_blocking_case(c["id"], {"first_appeal_decision": "заблокировано"})
        updated = storage.get_blocking_case(c["id"])
        self.assertEqual(updated["first_appeal_decision"], "заблокировано")
        self.assertEqual(updated["url"], "https://x.test/1")  # остальное не тронуто

    # --- защита от задвоения при параллельной работе нескольких сотрудников ---
    def test_adding_same_url_twice_is_rejected_not_duplicated(self):
        """Ключевой сценарий: двое сотрудников видят одну и ту же ссылку в
        выдаче и оба жмут «→ В блокировку» примерно одновременно — должно
        получиться одно дело, а не два."""
        first = storage.add_blocking_case({"url": "https://pirate.test/x", "title": "т"})
        second = storage.add_blocking_case({"url": "https://pirate.test/x", "title": "т"})
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        all_cases = storage.load_blocking_cases()
        self.assertEqual(len(all_cases), 1)

    def test_dedup_uses_normalized_url_not_literal_match(self):
        """Та же ссылка, но с завершающим слэшем или http вместо https —
        тоже должна считаться дублем (та же нормализация, что уже
        используется для результатов поиска по произведению)."""
        storage.add_blocking_case({"url": "https://pirate.test/x", "title": "т"})
        second = storage.add_blocking_case({"url": "http://pirate.test/x/", "title": "т"})
        self.assertIsNone(second)

    def test_different_urls_are_both_added(self):
        first = storage.add_blocking_case({"url": "https://pirate.test/a", "title": "т"})
        second = storage.add_blocking_case({"url": "https://pirate.test/b", "title": "т"})
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)

    def test_delete_cascades_to_screenshots_on_disk(self):
        c = storage.add_blocking_case({"url": "https://x.test/1", "title": "т"})
        os.makedirs(storage.SCREENSHOTS_DIR, exist_ok=True)
        fname = "shot_stored.png"
        with open(os.path.join(storage.SCREENSHOTS_DIR, fname), "wb") as f:
            f.write(b"fake png")
        storage.add_screenshot({"case_id": c["id"], "original_name": "shot.png",
                                 "stored_filename": fname, "description": "", "size": 8, "uploaded_at": 0})
        storage.delete_blocking_case(c["id"])
        self.assertFalse(os.path.exists(os.path.join(storage.SCREENSHOTS_DIR, fname)))
        self.assertEqual(storage.get_case_screenshots(c["id"]), [])


class TestAnalyticsOverrides(StorageTestCase):
    def test_empty_by_default(self):
        overrides = storage.load_analytics_overrides()
        self.assertEqual(overrides, {"detected": {}, "blocked": {}})

    def test_set_and_load_override(self):
        storage.set_analytics_override("detected", "2026-08", 15)
        overrides = storage.load_analytics_overrides()
        self.assertEqual(overrides["detected"]["2026-08"], 15)

    def test_set_value_none_removes_override(self):
        storage.set_analytics_override("blocked", "2026-08", 3)
        storage.set_analytics_override("blocked", "2026-08", None)
        overrides = storage.load_analytics_overrides()
        self.assertNotIn("2026-08", overrides["blocked"])

    def test_detected_and_blocked_overrides_are_independent(self):
        storage.set_analytics_override("detected", "2026-08", 15)
        storage.set_analytics_override("blocked", "2026-08", 3)
        overrides = storage.load_analytics_overrides()
        self.assertEqual(overrides["detected"]["2026-08"], 15)
        self.assertEqual(overrides["blocked"]["2026-08"], 3)

    def test_invalid_metric_raises(self):
        with self.assertRaises(ValueError):
            storage.set_analytics_override("не_метрика", "2026-08", 1)


class TestWorkResults(StorageTestCase):
    def test_add_and_delete_row(self):
        row = storage.add_work_result_row("work1", {"url": "https://x.test", "title": "т", "description": ""})
        data = storage.load_work_results("work1")
        self.assertEqual(len(data["items"]), 1)
        storage.delete_work_result_row("work1", row["id"])
        data = storage.load_work_results("work1")
        self.assertEqual(len(data["items"]), 0)

    def test_adding_same_url_twice_is_rejected_not_duplicated(self):
        """Регрессия: раньше защиты от дублей на бэкенде не было вообще —
        полагались только на проверку на фронтенде, которая не покрывает
        все пути добавления (например, из «Поиска по сайтам»)."""
        first = storage.add_work_result_row("work1", {"url": "https://x.test/dup", "title": "т", "description": ""})
        self.assertIsNotNone(first)
        second = storage.add_work_result_row("work1", {"url": "https://x.test/dup", "title": "другое название", "description": ""})
        self.assertIsNone(second)
        data = storage.load_work_results("work1")
        self.assertEqual(len(data["items"]), 1)

    def test_same_url_allowed_for_different_works(self):
        """Дубль проверяется в пределах ОДНОГО произведения, а не глобально —
        одна и та же ссылка вполне может относиться к разным произведениям."""
        storage.add_work_result_row("work1", {"url": "https://x.test/shared", "title": "т", "description": ""})
        second = storage.add_work_result_row("work2", {"url": "https://x.test/shared", "title": "т", "description": ""})
        self.assertIsNotNone(second)

    def test_trailing_slash_counts_as_same_url(self):
        """Регрессия на найденную несостыковку: раньше сравнивались только
        буквально одинаковые строки, и https://x.test/page и
        https://x.test/page/ считались бы разными ссылками."""
        storage.add_work_result_row("work1", {"url": "https://x.test/page", "title": "т", "description": ""})
        second = storage.add_work_result_row("work1", {"url": "https://x.test/page/", "title": "т", "description": ""})
        self.assertIsNone(second)
        self.assertEqual(len(storage.load_work_results("work1")["items"]), 1)

    def test_http_vs_https_counts_as_same_url(self):
        storage.add_work_result_row("work1", {"url": "http://x.test/page", "title": "т", "description": ""})
        second = storage.add_work_result_row("work1", {"url": "https://x.test/page", "title": "т", "description": ""})
        self.assertIsNone(second)

    def test_host_case_insensitive_but_path_case_sensitive(self):
        """Домен нечувствителен к регистру (так и есть в реальности DNS),
        а путь — намеренно чувствителен (перестраховка: путь технически
        МОЖЕТ быть регистрозависимым на некоторых серверах)."""
        storage.add_work_result_row("work1", {"url": "https://X.Test/Page", "title": "т", "description": ""})
        same_host_diff_case = storage.add_work_result_row("work1", {"url": "https://x.test/Page", "title": "т", "description": ""})
        self.assertIsNone(same_host_diff_case)  # домен в другом регистре — та же ссылка

        diff_path_case = storage.add_work_result_row("work1", {"url": "https://x.test/page", "title": "т", "description": ""})
        self.assertIsNotNone(diff_path_case)  # путь в другом регистре — намеренно считается другой ссылкой

    def test_query_string_matters(self):
        """?id=1 и ?id=2 — разные страницы, не дубли."""
        storage.add_work_result_row("work1", {"url": "https://x.test/page?id=1", "title": "т", "description": ""})
        second = storage.add_work_result_row("work1", {"url": "https://x.test/page?id=2", "title": "т", "description": ""})
        self.assertIsNotNone(second)

    def test_root_path_with_and_without_slash_are_same(self):
        storage.add_work_result_row("work1", {"url": "https://x.test", "title": "т", "description": ""})
        second = storage.add_work_result_row("work1", {"url": "https://x.test/", "title": "т", "description": ""})
        self.assertIsNone(second)

    def test_missing_results_file_returns_empty_not_error(self):
        data = storage.load_work_results("никогда-не-существовавшее-произведение")
        self.assertEqual(data["items"], [])
        self.assertFalse(data["is_fallback"])

    def test_backward_compat_with_old_plain_list_format(self):
        os.makedirs(storage.RESULTS_DIR, exist_ok=True)
        import json
        path = os.path.join(storage.RESULTS_DIR, "legacy.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump([{"id": "a", "url": "https://x.test", "title": "старый формат"}], f)
        data = storage.load_work_results("legacy")
        self.assertEqual(len(data["items"]), 1)
        self.assertFalse(data["is_fallback"])


class TestConcurrency(StorageTestCase):
    def test_concurrent_blocking_case_creation_loses_nothing(self):
        """Регрессионный тест на гонку данных: без удержания блокировки на
        весь цикл 'прочитать -> изменить -> записать' часть записей терялась
        бы при параллельной записи из разных потоков."""
        n_threads = 40
        errors = []

        def worker(i):
            try:
                storage.add_blocking_case({"url": f"https://x.test/{i}", "title": f"дело {i}"})
            except Exception as e:  # noqa
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(storage.load_blocking_cases()), n_threads)


class TestAuditLog(StorageTestCase):
    def test_log_action_records_entry(self):
        storage.log_action("иван", "удалил дело", "тестовое дело")
        entries = storage.load_audit_log()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["username"], "иван")

    def test_log_action_without_username_is_noop(self):
        storage.log_action(None, "что-то")
        entries = storage.load_audit_log()
        self.assertEqual(entries, [])

    def test_load_audit_log_returns_newest_first(self):
        storage.log_action("иван", "действие 1")
        storage.log_action("иван", "действие 2")
        entries = storage.load_audit_log()
        self.assertEqual(entries[0]["action"], "действие 2")


if __name__ == "__main__":
    unittest.main()
