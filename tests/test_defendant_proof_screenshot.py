"""Тесты /api/blocking-cases/<id>/screenshots/capture-defendant-proof —
автоматический снимок русскоязычного whois-сервиса (2ip.io, заполнение
формы) с запасным вариантом на rdap.org, если форма не сработала, и с
плашкой (домен/IP/ответчик/источник/дата), впечатанной прямо в картинку."""
import io
import os
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage, jobs, screenshot_capture  # noqa: E402


def _wait_until(predicate, timeout=5, interval=0.05):
    start = time.time()
    while time.time() - start < timeout:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _fake_png_bytes(size=(100, 60)):
    """Настоящие, валидные PNG-байты — нужно, потому что скриншот реально
    открывается через Pillow для печати плашки (image_stamp.py)."""
    from PIL import Image
    img = Image.new("RGB", size, (240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _fake_result(captured_url="https://2ip.io/"):
    return {
        "png_bytes": _fake_png_bytes(),
        "html": "<html>2ip.io result</html>",
        "captured_url": captured_url,
        "captured_at": time.time(),
    }


class TestDefendantProofScreenshot(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def test_refuses_without_ip_address(self):
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        resp = self.client.post(f"/api/blocking-cases/{case['id']}/screenshots/capture-defendant-proof")
        self.assertEqual(resp.status_code, 400)

    def test_refuses_with_placeholder_zero_ip(self):
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        storage.update_blocking_case(case["id"], {"ip_address": "0.0.0.0"})
        resp = self.client.post(f"/api/blocking-cases/{case['id']}/screenshots/capture-defendant-proof")
        self.assertEqual(resp.status_code, 400)

    def test_uses_2ip_io_form_by_default(self):
        """Ключевое изменение по вашей просьбе: русскоязычный источник
        (2ip.io), а не английская страница регистратора."""
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        storage.update_blocking_case(case["id"], {"ip_address": "1.2.3.4"})

        with patch("backend.app.screenshot_capture.capture_with_form_query", return_value=_fake_result()) as mock_form:
            start_resp = self.client.post(f"/api/blocking-cases/{case['id']}/screenshots/capture-defendant-proof")
            self.assertEqual(start_resp.status_code, 202)
            job_id = start_resp.get_json()["job_id"]
            self.assertTrue(_wait_until(lambda: jobs.get_screenshot_job(job_id)["status"] == "done"))
            poll_resp = self.client.get(f"/api/blocking-cases/{case['id']}/screenshots/capture-defendant-proof/{job_id}")

        self.assertTrue(mock_form.called)
        called_args = mock_form.call_args[0]
        self.assertEqual(called_args[0], "https://2ip.io/")
        self.assertEqual(called_args[1], "1.2.3.4")  # IP передан как значение для заполнения формы

        self.assertEqual(poll_resp.status_code, 200)
        shot = poll_resp.get_json()["screenshot"]
        self.assertEqual(shot["purpose"], "defendant_proof")
        self.assertIn("2ip.io", shot["description"])

    def test_falls_back_to_readable_summary_page_when_2ip_form_fails(self):
        """Если заполнение формы 2ip.io не удалось (сайт поменял разметку
        и т.п.) — должна сработать собственная читаемая страница-сводка на
        русском (не сырой JSON с rdap.org, как было раньше, и не английская
        страница) — построенная из уже имеющихся в деле данных."""
        case = storage.add_blocking_case({
            "title": "т", "url": "https://x.test/1", "author_name": "А",
            "defendant": "Podaon SIA", "defendant_email": "abuse@podaon.com",
        })
        storage.update_blocking_case(case["id"], {"ip_address": "1.2.3.4"})

        with patch("backend.app.screenshot_capture.capture_with_form_query",
                    side_effect=screenshot_capture.ScreenshotCaptureError("форма не найдена")), \
             patch("backend.app.screenshot_capture.capture", return_value=_fake_result("data:text/html;...")) as mock_fallback:
            start_resp = self.client.post(f"/api/blocking-cases/{case['id']}/screenshots/capture-defendant-proof")
            job_id = start_resp.get_json()["job_id"]
            self.assertTrue(_wait_until(lambda: jobs.get_screenshot_job(job_id)["status"] == "done"))
            poll_resp = self.client.get(f"/api/blocking-cases/{case['id']}/screenshots/capture-defendant-proof/{job_id}")

        self.assertTrue(mock_fallback.called)
        called_url = mock_fallback.call_args[0][0]
        self.assertTrue(called_url.startswith("data:text/html;charset=utf-8;base64,"))  # своя страница, не внешняя ссылка

        # декодируем и проверяем, что данные дела реально попали в страницу
        import base64
        b64_part = called_url.split(",", 1)[1]
        decoded_html = base64.b64decode(b64_part).decode("utf-8")
        self.assertIn("Podaon SIA", decoded_html)
        self.assertIn("abuse@podaon.com", decoded_html)
        self.assertIn("1.2.3.4", decoded_html)

        self.assertEqual(poll_resp.status_code, 200)
        shot = poll_resp.get_json()["screenshot"]
        self.assertIn("данные RDAP", shot["description"])
        self.assertIn("запасной", shot["description"])

    def test_saved_image_has_banner_stamped_taller_than_original(self):
        """Не только доверяем image_stamp.py по отдельным юнит-тестам —
        проверяем и здесь, на уровне всего эндпоинта, что итоговый файл
        реально больше исходного скриншота (значит плашка правда нанесена)."""
        from PIL import Image

        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        storage.update_blocking_case(case["id"], {"ip_address": "1.2.3.4"})
        fake = _fake_result()

        with patch("backend.app.screenshot_capture.capture_with_form_query", return_value=fake):
            start_resp = self.client.post(f"/api/blocking-cases/{case['id']}/screenshots/capture-defendant-proof")
            job_id = start_resp.get_json()["job_id"]
            self.assertTrue(_wait_until(lambda: jobs.get_screenshot_job(job_id)["status"] == "done"))
            self.client.get(f"/api/blocking-cases/{case['id']}/screenshots/capture-defendant-proof/{job_id}")

        shot = storage.get_case_screenshots(case["id"])[0]
        saved_path = os.path.join(storage.SCREENSHOTS_DIR, shot["stored_filename"])
        with Image.open(saved_path) as saved_img:
            saved_size = saved_img.size
        original_img = Image.open(io.BytesIO(fake["png_bytes"]))
        self.assertGreater(saved_size[1], original_img.size[1])
        self.assertEqual(saved_size[0], original_img.size[0])

    def test_does_not_duplicate_metadata_on_repeated_poll(self):
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        storage.update_blocking_case(case["id"], {"ip_address": "1.2.3.4"})

        with patch("backend.app.screenshot_capture.capture_with_form_query", return_value=_fake_result()):
            start_resp = self.client.post(f"/api/blocking-cases/{case['id']}/screenshots/capture-defendant-proof")
            job_id = start_resp.get_json()["job_id"]
            self.assertTrue(_wait_until(lambda: jobs.get_screenshot_job(job_id)["status"] == "done"))
            self.client.get(f"/api/blocking-cases/{case['id']}/screenshots/capture-defendant-proof/{job_id}")
            self.client.get(f"/api/blocking-cases/{case['id']}/screenshots/capture-defendant-proof/{job_id}")

        self.assertEqual(len(storage.get_case_screenshots(case["id"])), 1)

    def test_violation_screenshot_is_not_tagged_as_defendant_proof(self):
        """Обычный автоскриншот (кнопка «Сделать автоматический скриншот»
        самой страницы) по-прежнему помечается как «нарушение», использует
        обычный capture() без заполнения форм."""
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})

        violation_result = _fake_result(captured_url="https://x.test/1")
        with patch("backend.screenshot_capture.capture", return_value=violation_result):
            start_resp = self.client.post(f"/api/blocking-cases/{case['id']}/screenshots/capture")
            job_id = start_resp.get_json()["job_id"]
            self.assertTrue(_wait_until(lambda: jobs.get_screenshot_job(job_id)["status"] == "done"))
            self.client.get(f"/api/blocking-cases/{case['id']}/screenshots/capture/{job_id}")

        shots = storage.get_case_screenshots(case["id"])
        self.assertEqual(shots[0]["purpose"], "violation")


if __name__ == "__main__":
    unittest.main()
