"""End-to-end тест: прогоняет ПОЛНЫЙ жизненный цикл дела блокировки через
реальные HTTP-эндпоинты (Flask test client), а не отдельные функции по
одной. Ровно то, чего не хватало по самокритике — баги на стыке модулей
(как история с журналом фонового наблюдателя) ловятся именно такими
тестами, не изолированными юнит-тестами отдельных кусочков.

Единственное, что подменяется — сетевые вызовы вовне (netinfo.lookup,
requests.get для проверки доступности): реальная сеть в тестах недопустима,
но вся цепочка внутри приложения — через настоящие HTTP-запросы к
настоящим эндпоинтам, в том порядке, в каком это происходит в жизни.

Путь целиком:
  добавили ссылку → определился IP (мок) → загрузили скриншот →
  решение по претензии «нет реакции» → заполнили личные данные автора →
  подготовили заявление → отметили дату подачи → фоновая проверка
  находит ссылку всё ещё доступной → needs_resend → повторно подготовили
  заявление → отдельное дело реально заблокировали (первое обращение) →
  фоновая проверка находит его снова доступным → needs_resend встаёт само
  → завершили отчёт за месяц → заблокированное без needs_resend ушло в
  архив, заблокированное с needs_resend осталось активным →
  восстановили заархивированное обратно.
"""
import io
import os
import sys
import time
import unittest
import zipfile
from unittest.mock import patch, MagicMock

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage, author_personal_data, jobs  # noqa: E402


FAKE_NET_LOOKUP = {"ip_address": "203.0.113.10", "hosting_org": "Тестовый хостинг", "defendant_email": ""}


class TestFullCaseLifecycle(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def _days_ago(self, days):
        return time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))

    def test_full_lifecycle_via_real_endpoints(self):
        author = storage.upsert_author({"id": None, "name": "Сквозной Автор"})
        author_personal_data.save(author["id"], {"full_name": "Сквозной Автор"})

        # 1. Добавили ссылку — IP/хостинг должны определиться (сеть подменена)
        with patch("backend.app.netinfo.lookup", return_value=FAKE_NET_LOOKUP):
            resp = self.client.post("/api/blocking-cases", json={
                "url": "https://pirate.test/course",
                "author_name": author["name"],
                "work_title": "Курс",
                "title": "Курс на pirate.test",
            })
        self.assertEqual(resp.status_code, 201)
        case = resp.get_json()
        self.assertEqual(case["ip_address"], "203.0.113.10")
        self.assertEqual(case["defendant"], "Тестовый хостинг")

        # 2. Загрузили скриншот (ручной, не Playwright — тот требует реальный браузер)
        # Настоящие валидные PNG-байты, не произвольный текст: их реально
        # открывает Pillow при склейке скриншотов для заявления (см. ниже,
        # image_stamp.combine_vertically, добавлено 03.09).
        fake_png = io.BytesIO()
        Image.new("RGB", (100, 60), (200, 200, 200)).save(fake_png, format="PNG")
        resp = self.client.post(
            f"/api/blocking-cases/{case['id']}/screenshots",
            data={"file": (io.BytesIO(fake_png.getvalue()), "shot.png"), "description": "первая фиксация"},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(len(storage.get_case_screenshots(case["id"])), 1)

        # 3. Решение по претензии ещё не определено — ответчик пока не отреагировал
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"claim_decision": "нет реакции"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["claim_decision"], "нет реакции")

        # 4. Подготовили заявление — реальный docx+zip, включая документы/скриншоты
        # (подготовка асинхронная — см. tests/test_court_petition_endpoint.py
        # для полного объяснения нового контракта: POST даёт job_id, дальше
        # опрос статуса и отдельное скачивание)
        start_resp = self.client.post(f"/api/authors/{author['id']}/court-petition", json={"case_ids": [case["id"]]})
        self.assertEqual(start_resp.status_code, 202)
        job_id = start_resp.get_json()["job_id"]
        deadline = time.time() + 10
        while time.time() < deadline:
            poll_resp = self.client.get(f"/api/authors/{author['id']}/court-petition/{job_id}")
            if poll_resp.get_json()["status"] == "done":
                break
            time.sleep(0.05)
        else:
            self.fail("Фоновая задача подготовки заявления не завершилась за отведённое время")
        resp = self.client.get(f"/api/authors/{author['id']}/court-petition/{job_id}/download")
        self.assertEqual(resp.status_code, 200)
        zf = zipfile.ZipFile(io.BytesIO(resp.data))
        # Структура архива менялась дважды: сначала (см. заметку разработки,
        # п.2) — заявление и скриншоты нарушения объединили в одну папку
        # "нарушения/". Затем (см. заметку разработки, 03.09, п.9) —
        # отдельные файлы на каждое дело заменены на 2 общих склеенных
        # файла на всё заявление сразу (image_stamp.combine_vertically).
        self.assertIn("нарушения/заявление.docx", zf.namelist())
        self.assertIn("нарушения/скриншоты нарушений.png", zf.namelist())

        # 5. Сотрудник отмечает дату фактической подачи (14 дней назад — чтобы проверка уже «созрела»)
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"petition_filed_at": self._days_ago(20)})
        self.assertEqual(resp.status_code, 200)

        # 6. Фоновая проверка находит ссылку ВСЁ ЕЩЁ доступной — заявление не подействовало
        before_log = len(storage.load_audit_log(1000))
        with patch("requests.get", return_value=MagicMock(status_code=200)):
            jobs._check_due_cases_once()
        updated_case = storage.get_blocking_case(case["id"])
        self.assertEqual(updated_case["link_status"], "доступна")
        self.assertTrue(updated_case["needs_resend"])
        # и это должно было попасть в журнал (регрессия на найденный ранее баг)
        self.assertGreater(len(storage.load_audit_log(1000)), before_log)

        # 7. needs_resend позволяет выбрать дело повторно, несмотря на уже стоящую дату подачи
        resp = self.client.post(f"/api/authors/{author['id']}/court-petition", json={"case_ids": [case["id"]]})
        self.assertEqual(resp.status_code, 202)  # не отклонено как «уже подано» (202 — запущено в фоне)

        # 8. Отмечаем НОВУЮ дату подачи — мониторинг должен сброситься (needs_resend снят)
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"petition_filed_at": self._days_ago(1)})
        self.assertEqual(resp.status_code, 200)
        refreshed = resp.get_json()
        self.assertFalse(refreshed["needs_resend"])
        self.assertEqual(refreshed["link_checked_at"], "")

        # 9. Отдельное дело — реально заблокировано (по первому обращению),
        #    а через 14+ дней ссылка снова ожила
        resp = self.client.post("/api/blocking-cases", json={
            "url": "https://pirate2.test/course", "author_name": author["name"], "title": "Второй",
        })
        case2 = resp.get_json()
        self.client.put(f"/api/blocking-cases/{case2['id']}", json={
            "first_appeal_decision": "заблокировано", "block_date": self._days_ago(20),
        })
        with patch("requests.get", return_value=MagicMock(status_code=200)):
            jobs._check_due_cases_once()
        updated_case2 = storage.get_blocking_case(case2["id"])
        self.assertTrue(updated_case2["needs_resend"])  # встало само — общего поля «Статус» больше нет, решение осталось как было
        self.assertEqual(updated_case2["first_appeal_decision"], "заблокировано")

        # 10. Третье дело — по-настоящему заблокировано (по повторному
        #     обращению) и остаётся заблокированным
        resp = self.client.post("/api/blocking-cases", json={
            "url": "https://pirate3.test/course", "author_name": author["name"], "title": "Третий",
        })
        case3 = resp.get_json()
        block_month = self._days_ago(5)[:7]  # YYYY-MM
        self.client.put(f"/api/blocking-cases/{case3['id']}", json={
            "repeat_appeal_decision": "заблокировано", "block_date": self._days_ago(5),
        })

        # 11. Завершаем отчёт за месяц: case3 (заблокировано, needs_resend=False)
        #     архивируется, case2 (needs_resend=True) остаётся активным
        resp = self.client.post("/api/blocking-cases/monthly-report/finalize", json={"month": block_month})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(storage.get_blocking_case(case3["id"]))
        self.assertIsNotNone(storage.get_blocking_case(case2["id"]))

        # 12. Восстанавливаем заархивированное дело обратно
        archive = storage.get_report_archive_for_author(author["name"])
        archived_entry = next(e for e in archive if e["id"] == case3["id"])
        resp = self.client.post(f"/api/report-archive/{archived_entry['id']}/restore")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(storage.get_blocking_case(case3["id"]))


if __name__ == "__main__":
    unittest.main()
