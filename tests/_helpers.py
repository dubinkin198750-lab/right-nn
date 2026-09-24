"""Общий базовый класс для тестов, которым нужно изолированное хранилище.

Раньше список путей storage, которые нужно подменить на временную папку,
был скопирован в каждый файл тестов отдельно (test_storage.py, test_auth.py).
Скопированные списки разошлись: в одном не хватало USERS_FILE/INVITES_FILE,
и тесты писали данные прямо в реальную папку data/ проекта, если она
существовала на диске. Это было обнаружено и исправлено (2026-08) — но
правильное исправление не «быть внимательнее в следующий раз», а убрать
саму возможность скопировать список не полностью: теперь он определён
только здесь, и все файлы тестов наследуются от этого одного класса.

Если в storage.py появится новый файл/путь — его нужно будет добавить
только в один список ниже, а не искать все места, где он продублирован.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import storage, document_vault  # noqa: E402

# Единственный источник правды: все path-константы модуля storage, которые
# должны подменяться на время теста. Если забыть добавить сюда новый путь —
# тест либо явно упадёт (файла не будет в temp-папке), либо (в худшем
# случае) попробует писать в реальную data/ — вторую защиту от этого см.
# в assert внутри setUp ниже.
_STORAGE_PATH_ATTRS = [
    "AUTHORS_FILE", "WORKS_FILE", "BLOCKLIST_FILE", "SITES_FILE",
    "BLOCKING_CASES_FILE", "DOCUMENTS_META_FILE", "SCREENSHOTS_META_FILE",
    "AUDIT_LOG_FILE", "USERS_FILE", "INVITES_FILE", "REPORT_ARCHIVE_FILE",
    "BULK_SEARCH_BATCH_FILE", "EMPLOYEE_DOCUMENTS_META_FILE", "SETTINGS_FILE",
    "ANALYTICS_OVERRIDES_FILE",
    "COMPLAINT_SEND_LOG_FILE",
    "DOCUMENT_ACCESS_GRANTS_FILE",
    "SITE_ACCESS_GRANTS_FILE",
    "SITE_SEARCH_LAST_RESULT_FILE",
    "YANDEX_COMPARE_FILE",
]
_STORAGE_DIR_ATTRS = ["RESULTS_DIR", "DOCUMENTS_DIR", "SCREENSHOTS_DIR"]


class IsolatedStorageTestCase(unittest.TestCase):
    """Базовый класс: подменяет ВСЕ пути storage (файлы и папки) на временную
    директорию и восстанавливает их после теста. Наследуйтесь от этого класса
    вместо того, чтобы копировать список путей заново.

    Заодно подменяет document_vault.DATA_DIR — этот модуль намеренно не
    импортирует storage (см. его докстринг про циклический импорт), поэтому
    подмены storage.DATA_DIR ему недостаточно, нужна отдельная строчка.
    author_personal_data.py такой отдельной подмены не требует — он читает
    storage.DATA_DIR заново при каждом обращении, а не кеширует при импорте."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="piracy_monitor_test_")

        real_data_dir = os.path.dirname(storage.AUTHORS_FILE)
        # защита в глубину: если реальная data/ каким-то образом совпадёт с
        # temp-папкой (не должна, но на случай будущей правки этого файла) —
        # тест явно упадёт с понятной ошибкой, а не молча запишет тестовые
        # данные в настоящую папку проекта.
        assert self._tmp != real_data_dir, "temp-папка совпала с реальной data/ — не должно случиться"

        self._orig = {"DATA_DIR": storage.DATA_DIR, "DOCUMENT_VAULT_DATA_DIR": document_vault.DATA_DIR}
        for attr in _STORAGE_PATH_ATTRS:
            self._orig[attr] = getattr(storage, attr)
        for attr in _STORAGE_DIR_ATTRS:
            self._orig[attr] = getattr(storage, attr)

        storage.DATA_DIR = self._tmp
        document_vault.DATA_DIR = self._tmp
        for attr in _STORAGE_PATH_ATTRS:
            filename = attr.replace("_META_FILE", "").replace("_FILE", "").lower() + ".json"
            setattr(storage, attr, os.path.join(self._tmp, filename))
        for attr in _STORAGE_DIR_ATTRS:
            dirname = attr.replace("_DIR", "").lower()
            setattr(storage, attr, os.path.join(self._tmp, dirname))

    def tearDown(self):
        document_vault.DATA_DIR = self._orig["DOCUMENT_VAULT_DATA_DIR"]
        for k, v in self._orig.items():
            if k == "DOCUMENT_VAULT_DATA_DIR":
                continue
            setattr(storage, k, v)
        shutil.rmtree(self._tmp, ignore_errors=True)
