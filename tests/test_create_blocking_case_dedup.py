"""Тесты POST /api/blocking-cases — в первую очередь защита от задвоения:
если два сотрудника почти одновременно добавляют одну и ту же ссылку в
блокировку (например, оба смотрят на одну и ту же выдачу поиска), должно
получиться одно дело, а не два, и второй запрос должен получить понятную
ошибку, а не тихо создать дубль или упасть с 500."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


class TestCreateBlockingCaseDedup(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def _post(self, url):
        # netinfo.lookup делает реальные сетевые запросы (DNS/RDAP) — в
        # тестах подменяем на пустой результат, чтобы не зависеть от сети
        with patch("backend.app.netinfo.lookup", return_value={"ip_address": "", "hosting_org": "", "defendant_email": ""}):
            return self.client.post("/api/blocking-cases", json={"url": url, "title": "т", "author_name": "А"})

    def test_first_request_succeeds(self):
        resp = self._post("https://pirate.test/x")
        self.assertEqual(resp.status_code, 201)

    def test_second_request_same_url_gets_409_not_duplicate(self):
        """Ключевой сценарий из запроса пользователя: 2-3 человека
        работают над одной и той же ссылкой одновременно."""
        first = self._post("https://pirate.test/x")
        second = self._post("https://pirate.test/x")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertIn("error", second.get_json())

        all_cases = self.client.get("/api/blocking-cases").get_json()
        self.assertEqual(len(all_cases), 1)  # не два дела, ровно одно

    def test_three_near_simultaneous_requests_only_one_succeeds(self):
        """Именно «2-3 человека», как в вопросе — три подряд идущих
        запроса на одну и ту же ссылку, только первый должен пройти."""
        results = [self._post("https://pirate.test/y").status_code for _ in range(3)]
        self.assertEqual(results.count(201), 1)
        self.assertEqual(results.count(409), 2)
        all_cases = self.client.get("/api/blocking-cases").get_json()
        self.assertEqual(len([c for c in all_cases if c["url"] == "https://pirate.test/y"]), 1)

    def test_different_urls_both_succeed(self):
        first = self._post("https://pirate.test/a")
        second = self._post("https://pirate.test/b")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)

    def test_dedup_survives_trailing_slash_difference(self):
        first = self._post("https://pirate.test/x")
        second = self._post("https://pirate.test/x/")  # тот же адрес с завершающим слэшем
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)

    def _post_with_work(self, url, work_id, work_title="Курс", author_name="А"):
        with patch("backend.app.netinfo.lookup", return_value={"ip_address": "", "hosting_org": "", "defendant_email": ""}):
            return self.client.post("/api/blocking-cases", json={
                "url": url, "title": "т", "author_name": author_name, "work_title": work_title, "work_id": work_id,
            })

    def test_same_url_different_work_id_both_succeed(self):
        """Ключевой сценарий из обсуждения 03.09: уникальность теперь в
        рамках одного произведения, не глобальная — та же ссылка легально
        может относиться сразу к двум разным произведениям (например,
        складчина-страница продаёт несколько курсов одного автора)."""
        first = self._post_with_work("https://bundle.test/x", work_id="work-1", work_title="Курс А")
        second = self._post_with_work("https://bundle.test/x", work_id="work-2", work_title="Курс Б")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        all_cases = self.client.get("/api/blocking-cases").get_json()
        self.assertEqual(len([c for c in all_cases if c["url"] == "https://bundle.test/x"]), 2)

    def test_same_url_same_work_id_still_rejected(self):
        """А вот в рамках ОДНОГО и того же произведения — по-прежнему
        нельзя дважды, как и раньше."""
        first = self._post_with_work("https://bundle.test/y", work_id="work-1")
        second = self._post_with_work("https://bundle.test/y", work_id="work-1")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)

    def test_same_url_missing_work_id_on_either_side_falls_back_to_rejected(self):
        """Если у одного из двух дел (нового или уже существующего)
        work_id не указан вообще — нельзя надёжно понять, «то же
        произведение или нет» — подстраховываемся в сторону отказа
        (прежнее, более строгое поведение), а не разрешаем вслепую."""
        first = self._post("https://bundle.test/z")  # без work_id вообще
        second = self._post_with_work("https://bundle.test/z", work_id="work-1")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)


if __name__ == "__main__":
    unittest.main()
