"""Тест на автоподстановку поля discovered_at («Дата обнаружения») при
создании дела блокировки — раньше сотрудник должен был проставлять эту
дату вручную (пустое поле по умолчанию), хотя по факту это почти всегда
«сегодня», раз ссылка добавляется в момент обнаружения. Теперь
подставляется автоматически сегодняшним числом сервера, но остаётся
обычным редактируемым полем — тот же принцип, что и у автоподстановки
block_date (см. tests/test_auto_archive_on_blocked.py)."""
import os
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


class TestDiscoveredAtAutofill(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def _fake_lookup(self):
        return {"ip_address": "", "hosting_org": "", "defendant_email": "", "defendant_address": ""}

    def test_discovered_at_defaults_to_today_on_creation(self):
        with patch("backend.app.netinfo.lookup", return_value=self._fake_lookup()):
            resp = self.client.post("/api/blocking-cases", json={
                "url": "https://pirate.test/discovered-1", "title": "т", "author_name": "А",
            })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["discovered_at"], time.strftime("%Y-%m-%d"))

    def test_explicit_discovered_at_from_caller_is_not_overwritten(self):
        """Если вызывающий (например, будущий импорт старых дел) уже
        прислал свою дату обнаружения — не должна затираться сегодняшней."""
        with patch("backend.app.netinfo.lookup", return_value=self._fake_lookup()):
            resp = self.client.post("/api/blocking-cases", json={
                "url": "https://pirate.test/discovered-2", "title": "т", "author_name": "А",
                "discovered_at": "2026-01-15",
            })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["discovered_at"], "2026-01-15")

    def test_discovered_at_still_editable_after_creation(self):
        """Автоподстановка — не блокировка поля: сотрудник должен по-прежнему
        мочь поправить дату вручную (например, если реально нашёл ссылку
        раньше, чем успел завести дело)."""
        with patch("backend.app.netinfo.lookup", return_value=self._fake_lookup()):
            resp = self.client.post("/api/blocking-cases", json={
                "url": "https://pirate.test/discovered-3", "title": "т", "author_name": "А",
            })
        case_id = resp.get_json()["id"]
        patch_resp = self.client.put(f"/api/blocking-cases/{case_id}", json={"discovered_at": "2026-02-01"})
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(storage.get_blocking_case(case_id)["discovered_at"], "2026-02-01")


if __name__ == "__main__":
    unittest.main()
