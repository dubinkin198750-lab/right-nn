"""Тесты /api/authors/<id>/court-petition — в первую очередь правило
о повторной подаче: обычно нельзя выбрать уже поданное дело снова,
но можно, если ссылка «ожила» и needs_resend выставлен.

Подготовка теперь асинхронная (см. backend/jobs.py, start_petition_job) —
POST сразу отвечает 202 и job_id, а не готовым файлом. Хелпер
_prepare_and_download ниже эмулирует то же самое, что делает фронтенд:
запускает, дожидается статуса "done", скачивает результат — и уже
возвращает финальный Response, чтобы остальные проверки (код ответа,
содержимое zip, заголовки) остались такими же, как были."""
import io
import os
import sys
import time
import unittest
import zipfile
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage, author_personal_data  # noqa: E402


class TestCourtPetitionEndpoint(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

        self.author = storage.upsert_author({"id": None, "name": "Автор Тестов"})
        author_personal_data.save(self.author["id"], {"full_name": "Автор Тестов"})

    def _case(self, **overrides):
        base = {"title": "т", "url": "https://x.test/1", "author_name": self.author["name"]}
        base.update(overrides)
        return storage.add_blocking_case(base)

    def _start_petition(self, case_ids):
        return self.client.post(
            f"/api/authors/{self.author['id']}/court-petition",
            json={"case_ids": case_ids},
        )

    def _prepare_and_download(self, case_ids, timeout=10):
        """Запускает подготовку, дожидается завершения фоновой задачи (в
        тестах она выполняется в отдельном демон-потоке почти мгновенно —
        никакого реального Chromium/сети тут нет), возвращает финальный
        Response со скачанным файлом. Если сборка вернула ошибку (4xx) —
        возвращает этот ответ как есть, без попытки опроса/скачивания."""
        start_resp = self._start_petition(case_ids)
        if start_resp.status_code >= 400:
            return start_resp
        job_id = start_resp.get_json()["job_id"]

        deadline = time.time() + timeout
        while time.time() < deadline:
            poll_resp = self.client.get(f"/api/authors/{self.author['id']}/court-petition/{job_id}")
            status = poll_resp.get_json()["status"]
            if status == "error":
                # эмулируем прежний код ответа при ошибке сборки — тесты
                # ниже проверяют только текст ошибки, не точный код
                poll_resp.status_code = 400
                return poll_resp
            if status == "done":
                break
            time.sleep(0.05)
        else:
            self.fail("Фоновая задача подготовки заявления не завершилась за отведённое время")

        return self.client.get(f"/api/authors/{self.author['id']}/court-petition/{job_id}/download")

    def test_already_filed_case_without_needs_resend_is_rejected(self):
        case = self._case()
        storage.update_blocking_case(case["id"], {"petition_filed_at": "2026-07-01", "needs_resend": False})

        resp = self._start_petition([case["id"]])
        self.assertEqual(resp.status_code, 400)
        self.assertIn("уже отмечено как поданное", resp.get_json()["error"])

    def test_already_filed_case_with_needs_resend_is_allowed(self):
        case = self._case()
        storage.update_blocking_case(case["id"], {"petition_filed_at": "2026-07-01", "needs_resend": True})

        resp = self._prepare_and_download([case["id"]])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/zip")

    def test_already_filed_case_with_rkn_rejected_is_allowed(self):
        """Решение РКН «отклонено» само по себе — тоже сигнал «нужно
        переподавать», не нужно ждать ещё и needs_resend от проверки
        ссылки."""
        case = self._case()
        storage.update_blocking_case(case["id"], {
            "petition_filed_at": "2026-07-01", "needs_resend": False, "first_appeal_decision": "отклонено",
        })
        resp = self._prepare_and_download([case["id"]])
        self.assertEqual(resp.status_code, 200)

    def test_already_filed_case_with_rkn_no_response_is_allowed(self):
        case = self._case()
        storage.update_blocking_case(case["id"], {
            "petition_filed_at": "2026-07-01", "needs_resend": False, "first_appeal_decision": "нет реакции",
        })
        resp = self._prepare_and_download([case["id"]])
        self.assertEqual(resp.status_code, 200)

    def test_already_filed_case_with_rkn_blocked_decision_is_still_rejected(self):
        """А вот «заблокировано» в решении РКН — это НЕ провал обращения,
        наоборот, оно сработало; повторную подготовку заявления такое
        решение само по себе разрешать не должно (нужен именно needs_resend
        от проверки ссылки, вдруг блокировка перестала действовать)."""
        case = self._case()
        storage.update_blocking_case(case["id"], {
            "petition_filed_at": "2026-07-01", "needs_resend": False, "first_appeal_decision": "заблокировано",
        })
        resp = self._start_petition([case["id"]])
        self.assertEqual(resp.status_code, 400)

    def test_never_filed_case_is_allowed(self):
        case = self._case()
        resp = self._prepare_and_download([case["id"]])
        self.assertEqual(resp.status_code, 200)

    def test_result_is_valid_zip_containing_petition(self):
        case = self._case()
        resp = self._prepare_and_download([case["id"]])
        zf = zipfile.ZipFile(io.BytesIO(resp.data))
        # Структура архива изменилась (см. заметку разработки, п.2) — теперь
        # заявление лежит внутри папки "нарушения/", не в корне архива.
        self.assertIn("нарушения/заявление.docx", zf.namelist())

    def test_violation_and_defendant_proof_screenshots_go_to_different_folders(self):
        """Регрессия: скриншот нарушения и скриншот-подтверждение хостинга —
        разные по смыслу доказательства, не должны попасть в один и тот же
        файл.

        Структура архива менялась дважды: сначала (см. заметку разработки,
        п.2) — раньше было 2 отдельные папки ("скриншоты нарушения/",
        "подтверждение хостинга-ответчика/"), стало — одна папка
        "нарушения/" с меткой в имени файла. Затем (см. заметку
        разработки, 03.09, п.9) — отдельные файлы на каждое дело заменены
        на 2 общих склеенных файла на всё заявление сразу
        (image_stamp.combine_vertically), поэтому проверяем уже не
        исходные имена файлов (их больше нет — они склеены), а сам факт,
        что оба файла существуют и это два РАЗНЫХ файла."""
        case = self._case()
        storage.add_screenshot({
            "case_id": case["id"], "original_name": "violation.png", "stored_filename": "violation.png",
            "description": "", "size": 10, "uploaded_at": 0, "purpose": "violation",
        })
        storage.add_screenshot({
            "case_id": case["id"], "original_name": "whois.png", "stored_filename": "whois.png",
            "description": "", "size": 10, "uploaded_at": 0, "purpose": "defendant_proof",
        })
        # сами файлы физически должны существовать на диске, иначе сборщик их пропустит —
        # настоящие валидные PNG-байты, не просто произвольный текст: их
        # реально открывает Pillow при склейке (image_stamp.combine_vertically)
        os.makedirs(storage.SCREENSHOTS_DIR, exist_ok=True)
        for fname, color in (("violation.png", (255, 0, 0)), ("whois.png", (0, 255, 0))):
            img = Image.new("RGB", (100, 60), color)
            with open(os.path.join(storage.SCREENSHOTS_DIR, fname), "wb") as f:
                img.save(f, format="PNG")

        resp = self._prepare_and_download([case["id"]])
        names = zipfile.ZipFile(io.BytesIO(resp.data)).namelist()
        self.assertIn("нарушения/скриншоты нарушений.png", names)
        self.assertIn("нарушения/скриншоты IP-хостинга.png", names)

    def test_multiple_cases_multiple_screenshots_all_combined_into_two_files(self):
        """Ключевой сценарий (см. заметку разработки, 03.09, п.9): выбрали
        несколько дел сразу, у каждого есть и скриншот нарушения, и
        скриншот подтверждения хостинга — в архиве должно получиться
        ровно 2 файла скриншотов (не по 2 на каждое дело), включающие
        снимки со ВСЕХ выбранных дел."""
        case1 = self._case(url="https://x.test/multi-1")
        case2 = self._case(url="https://x.test/multi-2")
        for case, color in ((case1, (255, 0, 0)), (case2, (0, 255, 0))):
            for purpose, fname_prefix in (("violation", "v"), ("defendant_proof", "w")):
                fname = f"{fname_prefix}_{case['id']}.png"
                storage.add_screenshot({
                    "case_id": case["id"], "original_name": fname, "stored_filename": fname,
                    "description": "", "size": 10, "uploaded_at": 0, "purpose": purpose,
                })
                os.makedirs(storage.SCREENSHOTS_DIR, exist_ok=True)
                img = Image.new("RGB", (100, 60), color)
                with open(os.path.join(storage.SCREENSHOTS_DIR, fname), "wb") as f:
                    img.save(f, format="PNG")

        resp = self._prepare_and_download([case1["id"], case2["id"]])
        names = zipfile.ZipFile(io.BytesIO(resp.data)).namelist()
        violation_files = [n for n in names if "скриншоты нарушений" in n]
        ip_files = [n for n in names if "скриншоты IP-хостинга" in n]
        self.assertEqual(len(violation_files), 1, "должен быть ровно один общий файл скриншотов нарушений, не по одному на дело")
        self.assertEqual(len(ip_files), 1, "должен быть ровно один общий файл скриншотов IP-хостинга, не по одному на дело")

        # сама склеенная картинка должна вместить оба снимка нарушений (по одному от каждого дела)
        zf = zipfile.ZipFile(io.BytesIO(resp.data))
        combined = Image.open(io.BytesIO(zf.read(violation_files[0])))
        self.assertEqual(combined.height, 60 + 60 + 6)  # 2 скриншота по 60px высотой + разделитель 6px

    def test_one_petition_combines_cases_from_chronic_and_regular_groups(self):
        """П.11 из обсуждения 03.09: должна быть возможность собрать ОДНО
        заявление сразу из ссылок «Постоянно блокируемых» и обычной
        «Блокировки». На бэкенде эти два раздела вообще не различаются —
        «постоянно блокируемая» ссылка это чисто фронтенд-фильтр
        (state.chronicActiveIds, см. app.js), эндпоинт подготовки
        заявления просто берёт произвольный список case_ids, какой ему
        передали. Здесь явно создаём именно такую смешанную ситуацию —
        2 дела, которые backend/chronic_links.py признал бы «постоянно
        блокируемыми» (тот же домен, то же произведение, 2+ повтора), и
        одно обычное несвязанное дело — и проверяем, что все три
        попадают в один и тот же собранный docx."""
        chronic_case1 = self._case(url="https://s1.mirror-test.me/a", work_title="Курс")
        chronic_case2 = self._case(url="https://s2.mirror-test.me/b", work_title="Курс")
        regular_case = self._case(url="https://x.test/regular-unrelated-page")

        # подтверждаем, что первые два дела backend реально считает
        # хронической группой — иначе тест ничего не проверял бы всерьёз
        from backend import chronic_links
        groups = chronic_links.compute_chronic_domains()
        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0]["active_case_ids"]), {chronic_case1["id"], chronic_case2["id"]})
        self.assertNotIn(regular_case["id"], chronic_links.chronic_active_case_ids())

        resp = self._prepare_and_download([chronic_case1["id"], chronic_case2["id"], regular_case["id"]])
        self.assertEqual(resp.status_code, 200)
        zf = zipfile.ZipFile(io.BytesIO(resp.data))
        doc_bytes = zf.read("нарушения/заявление.docx")
        from docx import Document
        doc = Document(io.BytesIO(doc_bytes))
        full_text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("mirror-test.me/a", full_text)
        self.assertIn("mirror-test.me/b", full_text)
        self.assertIn("regular-unrelated-page", full_text)

    def test_case_from_different_author_is_rejected(self):
        other_author = storage.upsert_author({"id": None, "name": "Другой Автор"})
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/2", "author_name": other_author["name"]})
        resp = self._start_petition([case["id"]])
        self.assertEqual(resp.status_code, 400)

    def test_content_disposition_header_survives_real_http_encoding(self):
        """Регрессия на реальный баг, найденный вживую: Content-Disposition
        с кириллическим именем файла ронял сервер с UnicodeEncodeError при
        отправке по сети — HTTP-заголовки обязаны быть latin-1.

        Flask test_client() (как во всех остальных тестах этого файла) эту
        ошибку НЕ ловит — он работает в памяти процесса и не проходит через
        тот код (werkzeug.serving), который реально кодирует заголовки в
        байты при отправке по сокету. Поэтому здесь эта же проверка
        сделана напрямую — воспроизводит именно то условие, которое падает
        на настоящем сервере, без необходимости поднимать реальный сервер."""
        case = self._case()
        resp = self._prepare_and_download([case["id"]])
        self.assertEqual(resp.status_code, 200)
        header_value = resp.headers.get("Content-Disposition")
        self.assertIsNotNone(header_value)
        try:
            header_value.encode("latin-1")
        except UnicodeEncodeError:
            self.fail(
                f"Content-Disposition не кодируется в latin-1 (упадёт на реальном "
                f"сервере, хоть тестовый клиент этого не покажет): {header_value!r}"
            )


if __name__ == "__main__":
    unittest.main()
