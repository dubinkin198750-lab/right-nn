"""Тесты автоматического скриншота при обнаружении «постоянно
блокируемого» домена (см. app.py, _maybe_auto_capture_chronic /
_auto_capture_case_screenshots).

ОТКЛЮЧЕНО 16.09.2026 (см. комментарий в _maybe_auto_capture_chronic в
app.py) — именно этот незаметный для сотрудника автозапуск headless
Chromium при каждом новом повторе домена оказался главной причиной
падений сервера/100% нагрузки на минимальной VM. Тесты ниже раньше
проверяли, что автосъёмка срабатывает и досылается всем делам группы —
теперь наоборот следят, что она НЕ срабатывает вообще, ни при каких
условиях, чтобы случайное возвращение вызова осталось бы замечено."""
import io
import os
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


def _fake_png_bytes():
    from PIL import Image
    img = Image.new("RGB", (100, 60), (240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _fake_result(url="https://x.test/"):
    return {"png_bytes": _fake_png_bytes(), "html": "<html></html>", "captured_url": url, "captured_at": time.time()}


class TestChronicAutoCapture(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def test_domain_becoming_chronic_does_not_trigger_screenshots(self):
        """Раньше (до 16.09) обе ссылки группы получали автоскриншот, как
        только домен переходил порог «постоянно блокируемого». Теперь
        автозапуск отключён — ни старое, ни новое дело группы не должны
        получить ни одного скриншота, даже когда домен точно стал
        хроническим."""
        with patch("backend.netinfo.lookup", return_value={"ip": "", "defendant": "", "defendant_email": "", "defendant_address": ""}), \
             patch("backend.app.screenshot_capture.capture", return_value=_fake_result()) as mock_capture:
            resp1 = self.client.post("/api/blocking-cases", json={
                "url": "https://s1.chronic-test.me/a", "author_name": "Автор", "work_title": "Курс", "title": "т",
            })
            self.assertEqual(resp1.status_code, 201)
            case1_id = resp1.get_json()["id"]

            resp2 = self.client.post("/api/blocking-cases", json={
                "url": "https://s2.chronic-test.me/b", "author_name": "Автор", "work_title": "Курс", "title": "т",
            })
            self.assertEqual(resp2.status_code, 201)
            case2_id = resp2.get_json()["id"]

        time.sleep(0.3)  # дать фоновому потоку шанс сработать, если бы автоматика ошибочно вернулась
        self.assertEqual(len(storage.get_case_screenshots(case1_id)), 0,
                          "старое дело группы получило автоскриншот — автоматический триггер снова включён?")
        self.assertEqual(len(storage.get_case_screenshots(case2_id)), 0,
                          "новое дело получило автоскриншот — автоматический триггер снова включён?")
        mock_capture.assert_not_called()

    def test_domain_still_added_to_site_directory_when_chronic(self):
        """Отключили только съёмку скриншотов — добавление домена в
        справочник «Поиск по сайтам» при пересечении порога (отдельная,
        не связанная с Chromium логика) должно продолжать работать как
        раньше."""
        with patch("backend.netinfo.lookup", return_value={"ip": "", "defendant": "", "defendant_email": "", "defendant_address": ""}):
            self.client.post("/api/blocking-cases", json={
                "url": "https://s1.site-directory-test.me/a", "author_name": "Автор", "work_title": "Курс", "title": "т",
            })
            self.client.post("/api/blocking-cases", json={
                "url": "https://s2.site-directory-test.me/b", "author_name": "Автор", "work_title": "Курс", "title": "т",
            })

        sites = storage.load_sites()
        self.assertTrue(
            any("site-directory-test.me" in (s.get("url_template") or "") for s in sites),
            "домен, ставший «постоянно блокируемым», не попал в справочник «Поиск по сайтам»",
        )

    def test_case_with_existing_screenshot_is_not_touched(self):
        """Дело с уже существующим (снятым вручную) скриншотом не должно
        получить второй — актуально и сейчас, раз ручные скриншоты
        по-прежнему работают."""
        case1 = storage.add_blocking_case({"title": "т", "url": "https://s1.already.me/a", "author_name": "Автор", "work_title": "Курс"})
        storage.add_screenshot({
            "case_id": case1["id"], "original_name": "manual.png", "stored_filename": "manual.png",
            "description": "снято вручную", "size": 10, "uploaded_at": 0, "purpose": "violation",
        })

        with patch("backend.netinfo.lookup", return_value={"ip": "", "defendant": "", "defendant_email": "", "defendant_address": ""}), \
             patch("backend.app.screenshot_capture.capture", return_value=_fake_result()):
            resp2 = self.client.post("/api/blocking-cases", json={
                "url": "https://s2.already.me/b", "author_name": "Автор", "work_title": "Курс", "title": "т",
            })
            self.assertEqual(resp2.status_code, 201)

        time.sleep(0.3)
        self.assertEqual(len(storage.get_case_screenshots(case1["id"])), 1, "у дела с уже существующим скриншотом не должно появиться второго")

    def test_single_case_below_threshold_gets_no_screenshot(self):
        """Контрольный случай — без сюрпризов: одна ссылка своего домена,
        порог не пройден, автоскриншот не должен запускаться вообще (и
        подавно, раз автоматика теперь отключена целиком)."""
        with patch("backend.netinfo.lookup", return_value={"ip": "", "defendant": "", "defendant_email": "", "defendant_address": ""}), \
             patch("backend.app.screenshot_capture.capture", return_value=_fake_result()) as mock_capture:
            resp = self.client.post("/api/blocking-cases", json={
                "url": "https://onesite.example/x", "author_name": "Автор", "work_title": "Курс", "title": "т",
            })
            self.assertEqual(resp.status_code, 201)
            case_id = resp.get_json()["id"]

        time.sleep(0.3)
        self.assertEqual(len(storage.get_case_screenshots(case_id)), 0)
        mock_capture.assert_not_called()


if __name__ == "__main__":
    unittest.main()
