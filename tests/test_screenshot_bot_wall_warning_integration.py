"""Тесты того, что предупреждение «похоже на антибот-проверку/капчу»
действительно попадает в описание СОХРАНЁННОГО скриншота (не только сама
функция-детектор в screenshot_capture.py — см. test_screenshot_failure_detection.py
для юнит-тестов детектора отдельно)."""
import io
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402
from backend.app import _save_violation_screenshot, _save_defendant_proof_screenshot  # noqa: E402


def _fake_png_bytes():
    from PIL import Image
    img = Image.new("RGB", (100, 60), (240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _result(html, captured_url="https://x.test/"):
    return {"png_bytes": _fake_png_bytes(), "html": html, "captured_url": captured_url, "captured_at": time.time()}


class TestBotWallWarningInSavedDescription(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        self.case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "Автор"})

    def test_violation_screenshot_gets_warning_when_bot_wall_detected(self):
        result = _result("<html><body>Подтвердите, что вы не робот</body></html>")
        meta = _save_violation_screenshot(self.case["id"], result)
        self.assertIn("антибот", meta["description"])

    def test_violation_screenshot_no_warning_for_normal_page(self):
        result = _result("<html><body>" + "<p>Обычный курс по программированию.</p>" * 20 + "</body></html>")
        meta = _save_violation_screenshot(self.case["id"], result)
        self.assertNotIn("антибот", meta["description"])

    def test_defendant_proof_screenshot_gets_warning_when_bot_wall_detected(self):
        result = _result("<html><body>captcha required</body></html>", captured_url="https://2ip.io/")
        ctx = {"domain": "x.test", "ip": "1.2.3.4", "defendant": "Cloudflare"}
        defendant_check = {"checked": False, "matches": True, "rdap_org": None}
        meta = _save_defendant_proof_screenshot(self.case["id"], self.case, result, ctx, "2ip.io", defendant_check)
        self.assertIn("антибот", meta["description"])

    def test_defendant_proof_screenshot_no_warning_for_normal_result(self):
        result = _result("<html><body>IP: 1.2.3.4, организация: Cloudflare Inc.</body></html>", captured_url="https://2ip.io/")
        ctx = {"domain": "x.test", "ip": "1.2.3.4", "defendant": "Cloudflare"}
        defendant_check = {"checked": False, "matches": True, "rdap_org": None}
        meta = _save_defendant_proof_screenshot(self.case["id"], self.case, result, ctx, "2ip.io", defendant_check)
        self.assertNotIn("антибот", meta["description"])

    def test_both_warnings_can_appear_together(self):
        """Расхождение RDAP И капча одновременно — обе пометки должны
        остаться, не перезаписывать друг друга."""
        result = _result("<html><body>Please verify you are human</body></html>", captured_url="https://2ip.io/")
        ctx = {"domain": "x.test", "ip": "1.2.3.4", "defendant": "Cloudflare"}
        defendant_check = {"checked": True, "matches": False, "rdap_org": "Другая организация"}
        meta = _save_defendant_proof_screenshot(self.case["id"], self.case, result, ctx, "2ip.io", defendant_check)
        self.assertIn("антибот", meta["description"])
        self.assertIn("RDAP", meta["description"])


if __name__ == "__main__":
    unittest.main()
