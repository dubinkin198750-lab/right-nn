import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import document_vault  # noqa: E402


class TestDocumentVault(IsolatedStorageTestCase):
    def test_save_and_read_roundtrip(self):
        document_vault.save_encrypted("a.pdf", b"original bytes")
        self.assertEqual(document_vault.read_decrypted("a.pdf"), b"original bytes")

    def test_file_on_disk_is_not_plaintext(self):
        document_vault.save_encrypted("secret.pdf", b"confidential passport data")
        path = os.path.join(document_vault._vault_dir(), "secret.pdf")
        with open(path, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"confidential passport data", raw)

    def test_read_missing_file_returns_none(self):
        self.assertIsNone(document_vault.read_decrypted("does-not-exist.pdf"))

    def test_delete_removes_file(self):
        document_vault.save_encrypted("b.pdf", b"x")
        path = os.path.join(document_vault._vault_dir(), "b.pdf")
        self.assertTrue(os.path.exists(path))
        document_vault.delete_encrypted("b.pdf")
        self.assertFalse(os.path.exists(path))

    def test_delete_missing_file_does_not_raise(self):
        document_vault.delete_encrypted("never-existed.pdf")  # просто не должно бросить исключение

    def test_migrate_plaintext_folder_encrypts_and_removes_source(self):
        plain_dir = os.path.join(self._tmp, "old_plaintext")
        os.makedirs(plain_dir)
        with open(os.path.join(plain_dir, "old.pdf"), "wb") as f:
            f.write(b"legacy unencrypted content")

        migrated = document_vault.migrate_plaintext_folder(plain_dir)

        self.assertEqual(migrated, ["old.pdf"])
        self.assertFalse(os.path.exists(os.path.join(plain_dir, "old.pdf")))
        self.assertEqual(document_vault.read_decrypted("old.pdf"), b"legacy unencrypted content")

    def test_key_is_created_once_and_reused(self):
        document_vault.save_encrypted("c.pdf", b"one")
        key_path = document_vault._vault_key_file()
        self.assertTrue(os.path.exists(key_path))
        with open(key_path, "rb") as f:
            key1 = f.read()
        document_vault.save_encrypted("d.pdf", b"two")
        with open(key_path, "rb") as f:
            key2 = f.read()
        self.assertEqual(key1, key2)

    def test_concurrent_writes_do_not_lose_or_corrupt_files(self):
        def worker(i):
            document_vault.save_encrypted(f"file_{i}.pdf", f"content {i}".encode())

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        for i in range(30):
            self.assertEqual(document_vault.read_decrypted(f"file_{i}.pdf"), f"content {i}".encode())


if __name__ == "__main__":
    import unittest
    unittest.main()
