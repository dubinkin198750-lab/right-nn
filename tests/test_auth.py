import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import auth, storage  # noqa: E402
from tests._helpers import IsolatedStorageTestCase  # noqa: E402


class AuthTestCase(IsolatedStorageTestCase):
    """Изолирует .env (APP_USERS) поверх общей изоляции storage из
    IsolatedStorageTestCase — сама изоляция путей описана только там,
    здесь только то, что специфично для этого файла тестов (APP_USERS)."""

    def setUp(self):
        super().setUp()
        self._orig_env = os.environ.get("APP_USERS")
        os.environ.pop("APP_USERS", None)

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("APP_USERS", None)
        else:
            os.environ["APP_USERS"] = self._orig_env
        super().tearDown()



class TestLegacyEnvUsers(AuthTestCase):
    def test_disabled_when_nothing_configured(self):
        self.assertFalse(auth.is_enabled())

    def test_enabled_when_env_users_configured(self):
        os.environ["APP_USERS"] = "иван:pass123"
        self.assertTrue(auth.is_enabled())

    def test_correct_login_ascii_password(self):
        os.environ["APP_USERS"] = "admin:secret123"
        self.assertEqual(auth.check_login("admin", "secret123"), "admin")

    def test_wrong_password_rejected(self):
        os.environ["APP_USERS"] = "admin:secret123"
        self.assertIsNone(auth.check_login("admin", "wrong"))

    def test_unknown_username_rejected(self):
        os.environ["APP_USERS"] = "admin:secret123"
        self.assertIsNone(auth.check_login("ghost", "secret123"))

    def test_cyrillic_password_does_not_crash(self):
        """Регрессия: hmac.compare_digest падал на не-ASCII паролях."""
        os.environ["APP_USERS"] = "иван:секретныйпароль123"
        self.assertEqual(auth.check_login("иван", "секретныйпароль123"), "admin")
        self.assertIsNone(auth.check_login("иван", "неверный"))

    def test_multiple_users_parsed(self):
        os.environ["APP_USERS"] = "иван:pass1,мария:pass2"
        self.assertEqual(auth.check_login("иван", "pass1"), "admin")
        self.assertEqual(auth.check_login("мария", "pass2"), "admin")
        self.assertIsNone(auth.check_login("иван", "pass2"))

    def test_env_users_always_get_admin_role(self):
        os.environ["APP_USERS"] = "иван:pass1"
        self.assertEqual(auth.check_login("иван", "pass1"), "admin")


class TestDynamicUsers(AuthTestCase):
    def test_created_user_can_log_in_with_assigned_role(self):
        pwd_hash = auth.hash_password("моймогучийпароль")
        storage.create_user("редактор1", pwd_hash, "editor")
        self.assertEqual(auth.check_login("редактор1", "моймогучийпароль"), "editor")

    def test_wrong_password_for_dynamic_user_rejected(self):
        pwd_hash = auth.hash_password("правильный")
        storage.create_user("вьювер1", pwd_hash, "viewer")
        self.assertIsNone(auth.check_login("вьювер1", "неправильный"))

    def test_is_enabled_true_once_any_dynamic_user_exists(self):
        self.assertFalse(auth.is_enabled())
        storage.create_user("admin1", auth.hash_password("x"), "admin")
        self.assertTrue(auth.is_enabled())

    def test_duplicate_username_rejected(self):
        storage.create_user("занято", auth.hash_password("x"), "admin")
        with self.assertRaises(ValueError):
            storage.create_user("занято", auth.hash_password("y"), "editor")

    def test_passwords_are_hashed_not_plaintext(self):
        pwd_hash = auth.hash_password("секрет123")
        self.assertNotIn("секрет123", pwd_hash)

    def test_update_user_role(self):
        u = storage.create_user("растущий", auth.hash_password("x"), "viewer")
        storage.update_user_role(u["id"], "editor")
        self.assertEqual(storage.get_user_by_id(u["id"])["role"], "editor")

    def test_delete_user_revokes_access(self):
        u = storage.create_user("временный", auth.hash_password("x"), "editor")
        storage.delete_user(u["id"])
        self.assertIsNone(auth.check_login("временный", "x"))

    def test_count_admins(self):
        storage.create_user("a1", auth.hash_password("x"), "admin")
        storage.create_user("a2", auth.hash_password("x"), "admin")
        storage.create_user("e1", auth.hash_password("x"), "editor")
        self.assertEqual(storage.count_admins(), 2)


class TestRoleRanking(unittest.TestCase):
    def test_admin_satisfies_all_minimums(self):
        self.assertTrue(auth.has_role_at_least("admin", "viewer"))
        self.assertTrue(auth.has_role_at_least("admin", "editor"))
        self.assertTrue(auth.has_role_at_least("admin", "admin"))

    def test_viewer_does_not_satisfy_editor(self):
        self.assertFalse(auth.has_role_at_least("viewer", "editor"))
        self.assertFalse(auth.has_role_at_least("viewer", "admin"))

    def test_editor_satisfies_editor_not_admin(self):
        self.assertTrue(auth.has_role_at_least("editor", "editor"))
        self.assertFalse(auth.has_role_at_least("editor", "admin"))

    def test_unknown_role_satisfies_nothing(self):
        self.assertFalse(auth.has_role_at_least("несуществующая", "viewer"))


class TestInvites(AuthTestCase):
    def test_create_and_fetch_invite(self):
        inv = storage.create_invite("editor", created_by="admin1")
        fetched = storage.get_invite(inv["token"])
        self.assertEqual(fetched["role"], "editor")
        self.assertFalse(fetched["used"])

    def test_invite_valid_before_use(self):
        inv = storage.create_invite("viewer", created_by="admin1")
        self.assertTrue(storage.is_invite_valid(inv))

    def test_invite_invalid_after_use(self):
        inv = storage.create_invite("viewer", created_by="admin1")
        storage.mark_invite_used(inv["token"], "новый_пользователь")
        refreshed = storage.get_invite(inv["token"])
        self.assertFalse(storage.is_invite_valid(refreshed))

    def test_invite_invalid_when_expired(self):
        inv = storage.create_invite("viewer", created_by="admin1")
        # искусственно "просрочим" приглашение
        invites = storage.load_invites()
        for i in invites:
            if i["token"] == inv["token"]:
                i["expires_at"] = 0
        storage.save_invites(invites)
        refreshed = storage.get_invite(inv["token"])
        self.assertFalse(storage.is_invite_valid(refreshed))

    def test_unknown_token_invalid(self):
        self.assertFalse(storage.is_invite_valid(storage.get_invite("несуществующий-токен")))

    def test_delete_invite(self):
        inv = storage.create_invite("editor", created_by="admin1")
        storage.delete_invite(inv["token"])
        self.assertIsNone(storage.get_invite(inv["token"]))


if __name__ == "__main__":
    unittest.main()
