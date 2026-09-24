"""Тесты backend/image_stamp.py — печать плашки (домен/IP/ответчик/
источник/дата) прямо на изображении скриншота."""
import io
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402
from backend import image_stamp  # noqa: E402


def _sample_png(size=(200, 100), color=(240, 240, 240)):
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestStampBanner(unittest.TestCase):
    def test_output_is_taller_than_input(self):
        original = _sample_png(size=(300, 150))
        stamped = image_stamp.stamp_banner(original, fields=[("Домен", "example.com")])
        stamped_img = Image.open(io.BytesIO(stamped))
        original_img = Image.open(io.BytesIO(original))
        self.assertGreater(stamped_img.size[1], original_img.size[1])

    def test_width_unchanged(self):
        original = _sample_png(size=(400, 200))
        stamped = image_stamp.stamp_banner(original, fields=[("Домен", "x")])
        stamped_img = Image.open(io.BytesIO(stamped))
        self.assertEqual(stamped_img.size[0], 400)

    def test_original_image_preserved_below_banner(self):
        """Сама картинка не обрезается и не искажается — только сдвигается
        вниз, освобождая место под плашку сверху."""
        original = _sample_png(size=(100, 50), color=(10, 20, 30))
        stamped = image_stamp.stamp_banner(original, fields=[("X", "y")])
        stamped_img = Image.open(io.BytesIO(stamped)).convert("RGB")
        # нижний правый угол исходного изображения должен быть виден внизу итогового
        bottom_right_original = Image.open(io.BytesIO(original)).convert("RGB").getpixel((99, 49))
        bottom_right_stamped = stamped_img.getpixel((99, stamped_img.size[1] - 1))
        self.assertEqual(bottom_right_original, bottom_right_stamped)

    def test_empty_field_values_are_skipped(self):
        """Пустая строка/None не должны рисовать пустую строку в плашке —
        меньше строк, меньше высота баннера."""
        original = _sample_png()
        stamped_with_empty = image_stamp.stamp_banner(original, fields=[("Домен", ""), ("IP", None), ("Ответчик", "X")])
        stamped_without_empty = image_stamp.stamp_banner(original, fields=[("Ответчик", "X")])
        img1 = Image.open(io.BytesIO(stamped_with_empty))
        img2 = Image.open(io.BytesIO(stamped_without_empty))
        self.assertEqual(img1.size, img2.size)  # одинаковая высота — пустые поля правда пропущены

    def test_more_fields_means_taller_banner(self):
        original = _sample_png()
        one_field = image_stamp.stamp_banner(original, fields=[("A", "1")])
        three_fields = image_stamp.stamp_banner(original, fields=[("A", "1"), ("B", "2"), ("C", "3")])
        img1 = Image.open(io.BytesIO(one_field))
        img3 = Image.open(io.BytesIO(three_fields))
        self.assertGreater(img3.size[1], img1.size[1])

    def test_capture_date_always_included(self):
        """Дата фиксации — не одно из полей fields, а добавляется всегда
        отдельно, даже если fields пустой список."""
        original = _sample_png()
        stamped = image_stamp.stamp_banner(original, fields=[], captured_at=time.time())
        img = Image.open(io.BytesIO(stamped))
        self.assertGreater(img.size[1], Image.open(io.BytesIO(original)).size[1])

    def test_cyrillic_does_not_raise(self):
        """Смысл всей затеи — русский текст (домен на кириллице, названия
        компаний) должен рендериться без ошибок, не выбрасывая исключение
        и не давая пустую/повреждённую картинку."""
        original = _sample_png()
        stamped = image_stamp.stamp_banner(original, fields=[
            ("Домен", "пример.рф"),
            ("Ответчик", "ООО Хостинг-Сервис"),
            ("Источник", "RIPE NCC (официальный регистратор)"),
        ])
        img = Image.open(io.BytesIO(stamped))
        self.assertGreater(img.size[1], 0)

    def test_result_is_valid_png(self):
        original = _sample_png()
        stamped = image_stamp.stamp_banner(original, fields=[("X", "y")])
        img = Image.open(io.BytesIO(stamped))
        self.assertEqual(img.format, "PNG")


if __name__ == "__main__":
    unittest.main()
