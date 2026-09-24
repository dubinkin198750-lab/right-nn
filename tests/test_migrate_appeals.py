"""Перенос обращений в новый формат не должен терять ни одного значения."""
import copy
import glob
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage, migrate_appeals, appeals  # noqa: E402

# Реальные виды записей со скриншотов и из старого импорта
LEGACY_CASES = [
    {"id": "c1", "url": "https://skladchina-ua.com/1", "author_name": "Андрианов", "title": "Фабрика клонов",
     "court_ruling_number": "04.08 2И-6684", "rkn_number": "2026-08-07-5171156", "rkn_filed_at": "2026-08-07",
     "first_appeal_decision": "нет реакции", "repeat_ruling": "25.08 2И-7238", "repeat_rkn_filed_at": "2026-08-28",
     "notes": "2026-08-28-517115", "defendant": "Cloudflare, Inc.", "petition_filed_at": "2026-08-01",
     "other_complaints": [{"id": "o1", "filed_at": "2026-08-02", "method": "VK"}]},
    {"id": "c2", "url": "https://s66.zapret.me/2", "author_name": "Андрианов", "title": "Фабрика клонов",
     "court_ruling_number": "30.07 2И-6626", "rkn_number": "2026-08-04-5", "rkn_filed_at": "2026-08-04",
     "first_appeal_decision": "заблокировано", "block_date": "2026-09-10", "needs_resend": True},
    {"id": "c3", "url": "https://a.test/3", "author_name": "Гордынец", "title": "1С",
     "court_ruling_number": "04.12 2И-1", "rkn_filed_at": "2027-01-10"},
    {"id": "c4", "url": "https://a.test/4", "author_name": "Гордынец", "title": "1С",
     "court_ruling_number": "04.08 2И-6684", "court_ruling_date": "2026-08-05"},
    {"id": "c5", "url": "https://a.test/5", "author_name": "Гордынец", "title": "1С",
     "repeat_ruling": "всплыла на другом домене example.org"},
    {"id": "c6", "url": "https://a.test/6", "author_name": "Королева", "title": "Причёски",
     "claim_date": "2026-09-01", "claim_decision": "отклонено"},
]


class TestMigrateAppeals(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        storage.save_blocking_cases(copy.deepcopy(LEGACY_CASES[:5]))
        storage.save_report_archive(copy.deepcopy(LEGACY_CASES[5:]) + [dict(copy.deepcopy(LEGACY_CASES[0]), id="arch1")])

    def _run(self, apply):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = migrate_appeals.run(apply)
        return code, buf.getvalue()

    def test_dry_run_changes_nothing(self):
        before = storage.load_blocking_cases()
        code, out = self._run(False)
        self.assertEqual(code, 0)
        self.assertEqual(storage.load_blocking_cases(), before)
        self.assertIn("Пробная проверка целостности: OK", out)

    def test_apply_keeps_every_original_value(self):
        code, out = self._run(True)
        self.assertEqual(code, 0, out)
        self.assertIn("Проверка целостности после записи: OK", out)
        after = {c["id"]: c for c in storage.load_blocking_cases() + storage.load_report_archive()}
        originals = {c["id"]: c for c in LEGACY_CASES}
        originals["arch1"] = dict(LEGACY_CASES[0], id="arch1")
        self.assertEqual(set(after), set(originals))
        for cid, orig in originals.items():
            new = after[cid]
            backup = new[appeals.LEGACY_BACKUP_KEY]
            for f in appeals.LEGACY_BACKUP_FIELDS:
                self.assertEqual(backup.get(f) or "", orig.get(f) or "", f"{cid}.{f}")
            for k, v in orig.items():
                if k not in appeals.LEGACY_APPEAL_FIELDS:
                    self.assertEqual(new.get(k), v, f"{cid}.{k} изменилось")

    def test_year_not_pushed_into_future(self):
        self._run(True)
        c3 = [c for c in storage.load_blocking_cases() if c["id"] == "c3"][0]
        self.assertEqual(c3["appeals"][0]["mgs_date"], "2026-12-04")

    def test_conflicting_dates_keep_text(self):
        self._run(True)
        c4 = [c for c in storage.load_blocking_cases() if c["id"] == "c4"][0]
        self.assertEqual(c4["appeals"][0]["mgs_date"], "2026-08-05")
        self.assertEqual(c4["appeals"][0]["mgs_number"], "04.08 2И-6684")

    def test_free_text_repeat_ruling_preserved(self):
        self._run(True)
        c5 = [c for c in storage.load_blocking_cases() if c["id"] == "c5"][0]
        self.assertEqual(c5["appeals"][1]["mgs_number"], "всплыла на другом домене example.org")

    def test_file_backups_created(self):
        self._run(True)
        self.assertEqual(len(glob.glob(storage.BLOCKING_CASES_FILE + ".before-appeals-*")), 1)
        self.assertEqual(len(glob.glob(storage.REPORT_ARCHIVE_FILE + ".before-appeals-*")), 1)

    def test_second_run_changes_nothing(self):
        self._run(True)
        once = storage.load_blocking_cases()
        code, out = self._run(True)
        self.assertEqual(storage.load_blocking_cases(), once)
        self.assertIn("Переносить нечего", out)

    def test_integrity_failure_restores_files(self):
        before_active = storage.load_blocking_cases()
        real_save = storage.save_blocking_cases

        def broken_save(cases):
            real_save(cases[:-1])  # «теряем» одно дело при записи

        with patch.object(storage, "save_blocking_cases", side_effect=broken_save):
            code, out = self._run(True)
        self.assertEqual(code, 1)
        self.assertIn("файлы возвращены из копий", out)
        self.assertEqual(storage.load_blocking_cases(), before_active)

    def test_reports_for_manual_check(self):
        _, out = self._run(False)
        self.assertIn("год подставлен автоматически", out)
        self.assertIn("в примечаниях похоже есть номер обращения", out)
        self.assertIn("расходится с датой определения", out)
        self.assertIn("s66.zapret.me", out)


class TestUiSaveKeepsBackup(IsolatedStorageTestCase):
    def test_first_appeals_save_from_ui_stores_backup(self):
        from backend.app import app
        client = app.test_client()
        with client.session_transaction() as s:
            s["username"], s["role"] = "editor1", "editor"
        storage.save_blocking_cases([copy.deepcopy(LEGACY_CASES[0])])
        client.put("/api/blocking-cases/c1", json={"appeals": [{"mgs_number": "другое"}]})
        saved = storage.get_blocking_case("c1")
        self.assertEqual(saved[appeals.LEGACY_BACKUP_KEY]["court_ruling_number"], "04.08 2И-6684")
        self.assertEqual(saved[appeals.LEGACY_BACKUP_KEY]["repeat_ruling"], "25.08 2И-7238")
        # второе сохранение копию не перезаписывает
        client.put("/api/blocking-cases/c1", json={"appeals": [{"mgs_number": "третье"}]})
        self.assertEqual(storage.get_blocking_case("c1")[appeals.LEGACY_BACKUP_KEY]["court_ruling_number"], "04.08 2И-6684")


if __name__ == "__main__":
    unittest.main()
