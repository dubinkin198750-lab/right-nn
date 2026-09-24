"""Тесты backend/reset_admin_password.py — вызываем run() напрямую,
подменяя getpass.getpass, чтобы не зависеть от реального ввода в терминал."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage, auth, reset_admin_password  # noqa: E402


class TestResetExistingAdmin(IsolatedStorageTestCase):
    def test_resets_password_of_existing_admin(self):
        user = storage.create_user("admin1", auth.hash_password("старый_пароль"), "admin")
        self.assertIsNotNone(auth.check_login("admin1", "старый_пароль"))

        with patch("getpass.getpass", side_effect=["новый_пароль_12345", "новый_пароль_12345"]):
            code = reset_admin_password.run(["admin1"])

        self.assertEqual(code, 0)
        self.assertIsNone(auth.check_login("admin1", "старый_пароль"))  # старый больше не работает
        self.assertEqual(auth.check_login("admin1", "новый_пароль_12345"), "admin")  # новый работает

    def test_mismatched_passwords_do_not_change_anything(self):
        storage.create_user("admin1", auth.hash_password("исходный_пароль"), "admin")
        with patch("getpass.getpass", side_effect=["один", "другой"]):
            code = reset_admin_password.run(["admin1"])
        self.assertEqual(code, 1)
        self.assertEqual(auth.check_login("admin1", "исходный_пароль"), "admin")  # не тронут

    def test_too_short_password_is_rejected(self):
        storage.create_user("admin1", auth.hash_password("исходный_пароль"), "admin")
        with patch("getpass.getpass", side_effect=["коротк", "коротк"]):
            code = reset_admin_password.run(["admin1"])
        self.assertEqual(code, 1)
        self.assertEqual(auth.check_login("admin1", "исходный_пароль"), "admin")

    def test_unknown_username_fails_cleanly(self):
        code = reset_admin_password.run(["призрак"])
        self.assertEqual(code, 1)

    def test_refuses_to_reset_non_admin_user(self):
        storage.create_user("editor1", auth.hash_password("пароль_редактора"), "editor")
        with patch("getpass.getpass", side_effect=["новый_пароль_123", "новый_пароль_123"]):
            code = reset_admin_password.run(["editor1"])
        self.assertEqual(code, 1)
        # пароль редактора не должен был измениться
        self.assertEqual(auth.check_login("editor1", "пароль_редактора"), "editor")


class TestCreateAdminWhenNoneExists(IsolatedStorageTestCase):
    def test_creates_admin_when_truly_none_exist(self):
        self.assertEqual(storage.count_admins(), 0)
        with patch("getpass.getpass", side_effect=["первый_пароль_123", "первый_пароль_123"]):
            code = reset_admin_password.run(["новый_админ", "--create"])
        self.assertEqual(code, 0)
        self.assertEqual(auth.check_login("новый_админ", "первый_пароль_123"), "admin")

    def test_refuses_to_create_when_admin_already_exists(self):
        storage.create_user("уже_есть", auth.hash_password("x" * 10), "admin")
        with patch("getpass.getpass", side_effect=["пароль_1234567", "пароль_1234567"]):
            code = reset_admin_password.run(["второй_админ", "--create"])
        self.assertEqual(code, 1)
        self.assertIsNone(auth.check_login("второй_админ", "пароль_1234567"))  # не создался

    def test_refuses_to_create_when_env_admin_exists(self):
        orig = os.environ.get("APP_USERS")
        os.environ["APP_USERS"] = "legacy:pass"
        try:
            with patch("getpass.getpass", side_effect=["пароль_1234567", "пароль_1234567"]):
                code = reset_admin_password.run(["второй_админ", "--create"])
            self.assertEqual(code, 1)
        finally:
            if orig is None:
                os.environ.pop("APP_USERS", None)
            else:
                os.environ["APP_USERS"] = orig


if __name__ == "__main__":
    unittest.main()
