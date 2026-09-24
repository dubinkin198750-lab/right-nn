"""Тесты на автозаполнение поля defendant_address из RDAP (netinfo.py) —
пункт 1 из запроса пользователя: адрес ответчика должен подтягиваться из
официального источника (RDAP регионального регистратора), не только
вручную, где регистратор его публикует."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


class TestDefendantAddressAutofill(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def _fake_lookup(self, address="101 Townsend Street, San Francisco, CA, 94107"):
        return {
            "ip_address": "104.16.0.1", "hosting_org": "Cloudflare, Inc.",
            "defendant_email": "abuse@cloudflare.com", "defendant_address": address,
        }

    def test_address_autofilled_on_case_creation(self):
        with patch("backend.app.netinfo.lookup", return_value=self._fake_lookup()):
            resp = self.client.post("/api/blocking-cases", json={
                "url": "https://pirate.test/x", "title": "т", "author_name": "А",
            })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["defendant_address"], "101 Townsend Street, San Francisco, CA, 94107")

    def test_no_address_from_rdap_leaves_field_empty_not_crash(self):
        """Многие провайдеры не публикуют адрес — не должно падать, поле
        просто остаётся пустым для ручного заполнения."""
        with patch("backend.app.netinfo.lookup", return_value=self._fake_lookup(address="")):
            resp = self.client.post("/api/blocking-cases", json={
                "url": "https://pirate.test/y", "title": "т", "author_name": "А",
            })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["defendant_address"], "")

    def test_manual_refresh_button_updates_address(self):
        """Кнопка «🔄 обновить» в интерфейсе — на случай, если сайт сменил
        хостинг, или адрес не удалось определить при создании."""
        with patch("backend.app.netinfo.lookup", return_value=self._fake_lookup(address="")):
            case = self.client.post("/api/blocking-cases", json={
                "url": "https://pirate.test/z", "title": "т", "author_name": "А",
            }).get_json()
        self.assertEqual(case["defendant_address"], "")

        with patch("backend.app.netinfo.lookup", return_value=self._fake_lookup()):
            resp = self.client.post(f"/api/blocking-cases/{case['id']}/lookup-ip")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["defendant_address"], "101 Townsend Street, San Francisco, CA, 94107")

    def test_creation_does_not_overwrite_manually_entered_address(self):
        """Если адрес уже вписан вручную при создании (в том же запросе) —
        автоопределение не должно его затирать, как и с полем defendant."""
        with patch("backend.app.netinfo.lookup", return_value=self._fake_lookup(address="Другой адрес, вписанный вручную")):
            resp = self.client.post("/api/blocking-cases", json={
                "url": "https://pirate.test/manual", "title": "т", "author_name": "А",
                "defendant_address": "Мой собственный адрес",
            })
        self.assertEqual(resp.get_json()["defendant_address"], "Мой собственный адрес")


if __name__ == "__main__":
    unittest.main()
