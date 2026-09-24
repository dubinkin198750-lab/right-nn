"""Тесты детекции неудачных автоскриншотов — раньше система тихо
сохраняла как обычный снимок и страницу внутренней ошибки браузера
(chrome-error://...), и капча-заглушку, без какого-либо предупреждения
(см. заметку разработки, 03.09 — реальные найденные примеры на живом
сервере)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import screenshot_capture  # noqa: E402


class TestLooksLikeInternalErrorPage(unittest.TestCase):
    def test_chrome_error_scheme_detected(self):
        self.assertTrue(screenshot_capture._looks_like_internal_error_page("chrome-error://chromewebdata/"))

    def test_chrome_scheme_detected(self):
        self.assertTrue(screenshot_capture._looks_like_internal_error_page("chrome://settings/"))

    def test_about_blank_detected(self):
        self.assertTrue(screenshot_capture._looks_like_internal_error_page("about:blank"))

    def test_empty_url_detected(self):
        self.assertTrue(screenshot_capture._looks_like_internal_error_page(""))
        self.assertTrue(screenshot_capture._looks_like_internal_error_page(None))

    def test_normal_https_url_not_detected(self):
        self.assertFalse(screenshot_capture._looks_like_internal_error_page("https://example.com/threads/123"))

    def test_normal_http_url_not_detected(self):
        self.assertFalse(screenshot_capture._looks_like_internal_error_page("http://pirate-site.example/page"))


class TestLooksLikeBotWall(unittest.TestCase):
    def _short_html(self, body_text):
        return f"<html><body><div>{body_text}</div></body></html>"

    def test_russian_captcha_phrase_detected(self):
        html = self._short_html("Подтвердите, что вы не робот")
        self.assertTrue(screenshot_capture.looks_like_bot_wall(html))

    def test_english_captcha_phrase_detected(self):
        html = self._short_html("Please verify you are human before continuing")
        self.assertTrue(screenshot_capture.looks_like_bot_wall(html))

    def test_cloudflare_challenge_detected(self):
        html = self._short_html("Checking your browser before accessing the site — Just a moment...")
        self.assertTrue(screenshot_capture.looks_like_bot_wall(html))

    def test_normal_page_content_not_flagged(self):
        html = "<html><body>" + "<p>Курс по программированию на Python, всё о разработке.</p>" * 50 + "</body></html>"
        self.assertFalse(screenshot_capture.looks_like_bot_wall(html))

    def test_empty_html_not_flagged(self):
        self.assertFalse(screenshot_capture.looks_like_bot_wall(""))
        self.assertFalse(screenshot_capture.looks_like_bot_wall(None))

    def test_long_html_with_marker_word_not_flagged(self):
        """Длинная страница, где слово из списка маркеров встретилось
        случайно (например, статья ПРО капчи) — не должна ошибочно
        считаться самой капча-заглушкой, у настоящих заглушек видимого
        текста всегда мало, даже если внутри много JS/CSS (см. тест ниже
        про капчу с большим встроенным JavaScript — там ровно наоборот:
        HTML длинный, а текста мало, и это ДОЛЖНО сработать)."""
        html = "<html><body>" + ("<p>Обычная статья про капчу и защиту от ботов.</p>" * 1000) + "</body></html>"
        self.assertGreater(len(html), 20_000)
        self.assertFalse(screenshot_capture.looks_like_bot_wall(html))

    def test_short_html_without_markers_not_flagged(self):
        html = self._short_html("Добро пожаловать на наш обычный маленький сайт")
        self.assertFalse(screenshot_capture.looks_like_bot_wall(html))

    def test_real_captcha_with_large_embedded_javascript_still_detected(self):
        """Реальный найденный случай на живом сервере (04.09): современные
        антибот-страницы (Cloudflare Turnstile, reCAPTCHA и подобные) часто
        содержат десятки тысяч символов встроенного JavaScript — раньше
        (когда порог считался по СЫРОМУ html) это заставляло эвристику
        пропускать настоящую капчу просто потому, что общая длина файла
        была большой, хотя видимого пользователю текста — одна строка."""
        big_js = "x" * 30_000
        html = f"<html><head><script>{big_js}</script></head><body><div>Подтвердите, что вы не робот</div></body></html>"
        self.assertGreater(len(html), 20_000)
        self.assertTrue(screenshot_capture.looks_like_bot_wall(html))

    def test_long_article_with_lots_of_inline_style_not_flagged(self):
        """Обратная проверка: много CSS/разметки, но настоящий длинный
        видимый текст (не капча) — не должно ложно сработать только
        из-за объёма стилей/тегов."""
        big_css = "x" * 10_000
        html = f"<html><head><style>{big_css}</style></head><body>" + ("<p>Обычная статья про капчу и защиту от ботов.</p>" * 100) + "</body></html>"
        self.assertFalse(screenshot_capture.looks_like_bot_wall(html))


if __name__ == "__main__":
    unittest.main()
