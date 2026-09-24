import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import author_personal_data as apd  # noqa: E402


SAMPLE = {
    "entity_type": "individual",
    "full_name": "Иванова Мария Сергеевна",
    "birth_date": "1990-01-01",
    "birth_place": "г. Москва",
    "passport": "00 00 000000",
    "issued_by": "ОВД района Тестовый",
    "snils": "000-000-000 00",
    "org_name": "",
    "org_inn": "",
    "org_kpp": "",
    "org_address": "",
    "org_representative": "",
    "customer_name": "",
    "customer_director": "",
    "contract_number": "",
    "contract_date": "",
    "monthly_fee": "",
}


class TestAuthorPersonalData(IsolatedStorageTestCase):
    def test_save_and_get_roundtrip(self):
        apd.save("author-1", SAMPLE)
        self.assertEqual(apd.get("author-1"), SAMPLE)

    def test_get_missing_author_returns_none(self):
        self.assertIsNone(apd.get("no-such-author"))

    def test_has_data(self):
        self.assertFalse(apd.has_data("author-2"))
        apd.save("author-2", SAMPLE)
        self.assertTrue(apd.has_data("author-2"))

    def test_file_on_disk_does_not_contain_plaintext(self):
        apd.save("author-3", SAMPLE)
        store_file = apd._store_file()
        with open(store_file, "r", encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("Иванова", raw)
        self.assertNotIn(SAMPLE["passport"], raw)

    def test_delete(self):
        apd.save("author-4", SAMPLE)
        self.assertTrue(apd.has_data("author-4"))
        apd.delete("author-4")
        self.assertFalse(apd.has_data("author-4"))

    def test_delete_missing_author_does_not_raise(self):
        apd.delete("never-existed")

    def test_missing_fields_default_to_empty_string(self):
        apd.save("author-5", {"full_name": "Только имя"})
        fields = apd.get("author-5")
        self.assertEqual(fields["full_name"], "Только имя")
        self.assertEqual(fields["passport"], "")
        self.assertEqual(fields["snils"], "")

    def test_separate_authors_do_not_overwrite_each_other(self):
        apd.save("author-6", {"full_name": "Автор Шесть"})
        apd.save("author-7", {"full_name": "Автор Семь"})
        self.assertEqual(apd.get("author-6")["full_name"], "Автор Шесть")
        self.assertEqual(apd.get("author-7")["full_name"], "Автор Семь")

    def test_update_overwrites_previous_value(self):
        apd.save("author-8", {"full_name": "Старое имя"})
        apd.save("author-8", {"full_name": "Новое имя"})
        self.assertEqual(apd.get("author-8")["full_name"], "Новое имя")

    def test_concurrent_saves_for_different_authors_do_not_lose_writes(self):
        def worker(i):
            apd.save(f"author_{i}", {"full_name": f"Автор {i}"})

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        for i in range(30):
            fields = apd.get(f"author_{i}")
            self.assertIsNotNone(fields, f"потеряна запись для author_{i}")
            self.assertEqual(fields["full_name"], f"Автор {i}")


if __name__ == "__main__":
    import unittest
    unittest.main()
