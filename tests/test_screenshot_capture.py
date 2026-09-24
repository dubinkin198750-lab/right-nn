"""Тесты backend/screenshot_capture.py — capture_with_form_query, в первую
очередь. Настоящие тесты через реальный Chromium (не моки) — страницы
задаются через data: URL, без выхода в интернет, но с реальным поведением
браузера (поэтому и был пойман нюанс с кодировкой при написании самих
этих тестов — data: URL без явного charset=utf-8 ломает кириллицу, это
не баг кода, а особенность способа тестирования, см. историю разработки)."""
import base64
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import screenshot_capture  # noqa: E402


def _data_url(html):
    return "data:text/html;charset=utf-8;base64," + base64.b64encode(html.encode("utf-8")).decode()


_FORM_PAGE = """
<html><head><meta charset="utf-8"></head><body>
<form>
  <input type="text" name="ip" id="ip-input">
  <button type="button" onclick="document.body.innerHTML='<h1>Результат для ' + document.getElementById('ip-input').value + '</h1>'">Проверить</button>
</form>
</body></html>
"""

_PAGE_WITHOUT_MATCHING_INPUT = """
<html><body><p>На этой странице нет поля ввода вообще.</p></body></html>
"""

_PAGE_WITH_INPUT_BUT_NO_BUTTON = """
<html><body><input type="text" name="ip"></body></html>
"""


class TestCaptureWithFormQuery(unittest.TestCase):
    def test_fills_input_clicks_button_and_captures_result(self):
        result = screenshot_capture.capture_with_form_query(
            _data_url(_FORM_PAGE), "203.0.113.5",
            input_selectors=['input[name="ip"]'],
            submit_selectors=['button:has-text("Проверить")'],
        )
        self.assertIn("203.0.113.5", result["html"])
        self.assertGreater(len(result["png_bytes"]), 0)
        self.assertIn("captured_at", result)

    def test_tries_selectors_in_order_until_one_matches(self):
        """Первый селектор в списке не подходит ('input[name="nope"]' не
        существует на странице) — должен попробовать следующий и найти его."""
        result = screenshot_capture.capture_with_form_query(
            _data_url(_FORM_PAGE), "8.8.8.8",
            input_selectors=['input[name="nope"]', 'input[name="ip"]'],
            submit_selectors=['button:has-text("Проверить")'],
        )
        self.assertIn("8.8.8.8", result["html"])

    def test_raises_clear_error_when_no_input_found(self):
        with self.assertRaises(screenshot_capture.ScreenshotCaptureError) as ctx:
            screenshot_capture.capture_with_form_query(
                _data_url(_PAGE_WITHOUT_MATCHING_INPUT), "1.2.3.4",
                input_selectors=['input[name="ip"]'],
                submit_selectors=['button:has-text("Проверить")'],
            )
        self.assertIn("поле ввода", str(ctx.exception))

    def test_raises_clear_error_when_no_submit_button_found(self):
        with self.assertRaises(screenshot_capture.ScreenshotCaptureError) as ctx:
            screenshot_capture.capture_with_form_query(
                _data_url(_PAGE_WITH_INPUT_BUT_NO_BUTTON), "1.2.3.4",
                input_selectors=['input[name="ip"]'],
                submit_selectors=['button:has-text("Проверить")'],
            )
        self.assertIn("кнопку", str(ctx.exception))

    def test_error_message_mentions_manual_upload_fallback(self):
        """Пользователь должен понимать, что делать, если автоматизация не
        сработала — не только «ошибка», а конкретная подсказка."""
        with self.assertRaises(screenshot_capture.ScreenshotCaptureError) as ctx:
            screenshot_capture.capture_with_form_query(
                _data_url(_PAGE_WITHOUT_MATCHING_INPUT), "1.2.3.4",
                input_selectors=['input[name="ip"]'],
                submit_selectors=['button:has-text("Проверить")'],
            )
        self.assertIn("Загрузить", str(ctx.exception))

    def test_completes_within_reasonable_time_not_minutes(self):
        """Регрессия на реальный найденный случай: запрос зависал на
        полминуты+ из-за ожидания полного «затишья сети» (networkidle) —
        на сайтах с рекламой/счётчиками оно может не наступать вообще.
        Теперь стратегия ожидания короче и с фиксированными таймаутами —
        весь цикл должен укладываться в разумные секунды даже с учётом
        всех промежуточных пауз."""
        import time as time_module
        start = time_module.time()
        screenshot_capture.capture_with_form_query(
            _data_url(_FORM_PAGE), "203.0.113.5",
            input_selectors=['input[name="ip"]'],
            submit_selectors=['button:has-text("Проверить")'],
        )
        elapsed = time_module.time() - start
        self.assertLess(elapsed, 15, f"Заняло {elapsed:.1f}с — подозрительно долго для простой тестовой страницы")


if __name__ == "__main__":
    unittest.main()
