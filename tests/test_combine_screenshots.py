"""Тесты image_stamp.combine_vertically — склейка нескольких скриншотов в
один файл при подготовке заявления (см. app.py, _build_petition_zip;
заметка разработки, 03.09, п.9)."""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from backend import image_stamp  # noqa: E402


def _png(width, height, color):
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestCombineVertically(unittest.TestCase):
    def test_empty_list_returns_none(self):
        self.assertIsNone(image_stamp.combine_vertically([]))

    def test_single_image_returned_unchanged_in_size(self):
        result = image_stamp.combine_vertically([_png(200, 100, (255, 0, 0))])
        img = Image.open(io.BytesIO(result))
        self.assertEqual(img.size, (200, 100))

    def test_two_same_width_images_stacked_with_separator(self):
        result = image_stamp.combine_vertically([_png(200, 100, (255, 0, 0)), _png(200, 150, (0, 255, 0))])
        img = Image.open(io.BytesIO(result))
        self.assertEqual(img.width, 200)
        # высота = сумма высот + разделительная полоса между ними
        self.assertEqual(img.height, 100 + 150 + image_stamp._COMBINE_SEPARATOR_HEIGHT)

    def test_three_images_stacked_with_two_separators(self):
        result = image_stamp.combine_vertically([_png(200, 50, (255, 0, 0)), _png(200, 60, (0, 255, 0)), _png(200, 70, (0, 0, 255))])
        img = Image.open(io.BytesIO(result))
        self.assertEqual(img.height, 50 + 60 + 70 + image_stamp._COMBINE_SEPARATOR_HEIGHT * 2)

    def test_different_widths_normalized_to_widest(self):
        """Более узкое изображение масштабируется вверх (не дополняется
        пустым полем) — итоговая ширина равна ширине самого широкого."""
        result = image_stamp.combine_vertically([_png(200, 100, (255, 0, 0)), _png(100, 50, (0, 0, 255))])
        img = Image.open(io.BytesIO(result))
        self.assertEqual(img.width, 200)

    def test_narrower_image_scaled_preserving_aspect_ratio(self):
        """100x50 (соотношение 2:1) при масштабировании до ширины 200
        должно стать 200x100, сохраняя то же соотношение сторон."""
        result = image_stamp.combine_vertically([_png(200, 40, (255, 0, 0)), _png(100, 50, (0, 0, 255))])
        img = Image.open(io.BytesIO(result))
        # 40 (первое, без изменений) + 100 (второе, масштабированное 100x50 -> 200x100) + разделитель
        self.assertEqual(img.height, 40 + 100 + image_stamp._COMBINE_SEPARATOR_HEIGHT)

    def test_corrupted_image_in_the_middle_is_skipped_not_fatal(self):
        """Один битый/повреждённый файл на диске не должен рушить всю
        склейку — остальные валидные скриншоты не должны потеряться
        из-за одного плохого файла где-то в списке."""
        result = image_stamp.combine_vertically([
            _png(200, 100, (255, 0, 0)),
            b"this is not a valid png file at all",
            _png(200, 80, (0, 255, 0)),
        ])
        self.assertIsNotNone(result)
        img = Image.open(io.BytesIO(result))
        # только 2 настоящих изображения вошли в склейку (100 + 80 + 1 разделитель)
        self.assertEqual(img.height, 100 + 80 + image_stamp._COMBINE_SEPARATOR_HEIGHT)

    def test_all_images_corrupted_returns_none(self):
        result = image_stamp.combine_vertically([b"garbage", b"also garbage"])
        self.assertIsNone(result)

    def test_result_is_valid_png(self):
        result = image_stamp.combine_vertically([_png(50, 50, (1, 2, 3))])
        img = Image.open(io.BytesIO(result))
        self.assertEqual(img.format, "PNG")


if __name__ == "__main__":
    unittest.main()
