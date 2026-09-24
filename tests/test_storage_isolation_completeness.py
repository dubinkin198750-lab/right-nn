"""Страховка от повторения одного конкретного класса бага: если в
backend/storage.py появляется новая константа вида
`ИМЯ = os.path.join(DATA_DIR, "...")` (новый файл/папка данных), а её
забыли дописать в список изоляции _STORAGE_PATH_ATTRS/_STORAGE_DIR_ATTRS
в tests/_helpers.py — тесты для этой константы будут молча писать данные
в РЕАЛЬНУЮ папку data/ проекта, а не во временную. Это уже случалось дважды
(USERS_FILE/INVITES_FILE в 2026-08, затем SITE_SEARCH_LAST_RESULT_FILE
чуть позже) — оба раза до того, как эта проверка была добавлена.

Это отдельный файл (а не тест внутри самого tests/_helpers.py), потому что
pytest по умолчанию собирает только файлы вида test_*.py — тест,
оставленный внутри _helpers.py, никогда бы не запустился автоматически.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from tests._helpers import _STORAGE_PATH_ATTRS, _STORAGE_DIR_ATTRS  # noqa: E402


class TestIsolationListIsComplete(unittest.TestCase):
    def test_every_data_dir_constant_is_isolated(self):
        storage_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "storage.py"
        )
        with open(storage_path, "r", encoding="utf-8") as f:
            source = f.read()
        declared = set(re.findall(r"^([A-Z][A-Z0-9_]*)\s*=\s*os\.path\.join\(DATA_DIR\s*,", source, re.MULTILINE))
        covered = set(_STORAGE_PATH_ATTRS) | set(_STORAGE_DIR_ATTRS)
        missing = declared - covered
        self.assertEqual(
            missing, set(),
            f"В backend/storage.py есть константы под DATA_DIR, не перечисленные в "
            f"_STORAGE_PATH_ATTRS/_STORAGE_DIR_ATTRS (tests/_helpers.py): {sorted(missing)}. "
            f"Без этого тесты для них будут писать в РЕАЛЬНУЮ папку data/ проекта."
        )


if __name__ == "__main__":
    unittest.main()
