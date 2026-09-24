"""Тесты журнала отправок (претензии, жалобы Avito/Google DMCA, заявления
в суд/РКН) — отдельного от общего журнала действий, доступного только
admin. Редакторы по-прежнему сами видят/заполняют эти поля в таблице
блокировки как обычно — этот журнал лишь дополнительно фиксирует те же
события в одном месте."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


class TestComplaintSendLogStorage(IsolatedStorageTestCase):
    def test_empty_log_by_default(self):
        self.assertEqual(storage.load_complaint_send_log(), [])

    def test_entry_is_recorded(self):
        storage.add_complaint_send_log_entry({
            "username": "editor1", "type": "claim", "case_id": "abc",
            "url": "https://pirate.test/x", "author_name": "А", "work_title": "К",
            "date_value": "2026-08-15",
        })
        entries = storage.load_complaint_send_log()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["username"], "editor1")
        self.assertEqual(entries[0]["type"], "claim")

    def test_most_recent_first(self):
        storage.add_complaint_send_log_entry({"username": "e1", "type": "claim", "case_id": "1"})
        storage.add_complaint_send_log_entry({"username": "e2", "type": "avito", "case_id": "2"})
        entries = storage.load_complaint_send_log()
        self.assertEqual(entries[0]["case_id"], "2")  # последняя запись первой
        self.assertEqual(entries[1]["case_id"], "1")


class TestComplaintSendLogEndpoint(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        from backend import auth
        storage.create_user("admin1", auth.hash_password("x" * 10), "admin")
        storage.create_user("editor1", auth.hash_password("x" * 10), "editor")
        self.client = app.test_client()

    def _as(self, username, role):
        with self.client.session_transaction() as sess:
            sess["username"] = username
            sess["role"] = role

    def test_admin_can_view(self):
        self._as("admin1", "admin")
        resp = self.client.get("/api/complaint-send-log")
        self.assertEqual(resp.status_code, 200)

    def test_editor_cannot_view(self):
        self._as("editor1", "editor")
        resp = self.client.get("/api/complaint-send-log")
        self.assertEqual(resp.status_code, 403)

    def test_viewer_cannot_view(self):
        self._as("editor1", "viewer")
        resp = self.client.get("/api/complaint-send-log")
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_cannot_view(self):
        resp = self.client.get("/api/complaint-send-log")
        self.assertIn(resp.status_code, (401, 403))

    def test_setting_claim_date_first_time_logs_entry(self):
        """Ключевой сценарий: редактор сам, как обычно, отмечает дату
        претензии (например, кнопкой ✉️) — это должно попасть в журнал
        отправок автоматически, без отдельного действия."""
        self._as("editor1", "editor")
        case = storage.add_blocking_case({
            "title": "т", "url": "https://pirate.test/x", "author_name": "Иванов",
            "work_title": "Курс",
        })
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"claim_date": "2026-08-15"})
        self.assertEqual(resp.status_code, 200)

        self._as("admin1", "admin")
        log = self.client.get("/api/complaint-send-log").get_json()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["type"], "claim")
        self.assertEqual(log[0]["username"], "editor1")
        self.assertEqual(log[0]["url"], "https://pirate.test/x")
        self.assertEqual(log[0]["author_name"], "Иванов")
        self.assertEqual(log[0]["work_title"], "Курс")
        self.assertIn("type_label", log[0])

    def test_changing_to_different_value_logs_as_new_send(self):
        """Осознанно изменённое поведение (было наоборот): изменение уже
        стоявшей даты на ДРУГУЮ дату теперь тоже считается отправкой —
        например, повторная жалоба после того, как первая не подействовала.
        Отличить «правка задним числом опечатки» от «реальная повторная
        отправка» по одним только данным невозможно — выбрали не терять
        реальные повторные отправки ценой изредка лишней записи в журнале."""
        self._as("editor1", "editor")
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        self.client.put(f"/api/blocking-cases/{case['id']}", json={"claim_date": "2026-08-01"})
        self.client.put(f"/api/blocking-cases/{case['id']}", json={"claim_date": "2026-08-02"})

        self._as("admin1", "admin")
        log = self.client.get("/api/complaint-send-log").get_json()
        self.assertEqual(len(log), 2)
        dates = {e["date_value"] for e in log}
        self.assertEqual(dates, {"2026-08-01", "2026-08-02"})

    def test_resubmitting_the_same_value_does_not_log_again(self):
        """А вот повторная отправка ТОГО ЖЕ самого PUT с уже стоявшим
        значением — реального изменения нет, значит и новой записи в
        журнале быть не должно."""
        self._as("editor1", "editor")
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        self.client.put(f"/api/blocking-cases/{case['id']}", json={"claim_date": "2026-08-01"})
        self.client.put(f"/api/blocking-cases/{case['id']}", json={"claim_date": "2026-08-01"})  # то же самое значение

        self._as("admin1", "admin")
        log = self.client.get("/api/complaint-send-log").get_json()
        self.assertEqual(len(log), 1)

    def test_all_six_flat_field_types_log_correctly(self):
        """«Другое» (включая Avito — теперь просто один из пунктов этого
        списка, как VK/YouTube/Telegram) больше не плоское поле в этом же
        PUT — у него свой список записей и свои эндпоинты, см.
        TestOtherComplaints ниже."""
        self._as("editor1", "editor")
        fields_and_types = [
            ("claim_date", "claim"), ("petition_filed_at", "petition"),
            ("repeat_petition_filed_at", "repeat_petition"), ("rkn_filed_at", "rkn"),
            ("repeat_rkn_filed_at", "repeat_rkn"), ("google_dmca_filed_at", "google_dmca"),
        ]
        for field, expected_type in fields_and_types:
            case = storage.add_blocking_case({"title": "т", "url": f"https://x.test/{field}", "author_name": "А"})
            self.client.put(f"/api/blocking-cases/{case['id']}", json={field: "2026-08-15"})

        self._as("admin1", "admin")
        log = self.client.get("/api/complaint-send-log").get_json()
        logged_types = {e["type"] for e in log}
        self.assertEqual(logged_types, {t for _, t in fields_and_types})

    def test_non_tracked_field_change_does_not_log(self):
        """Правка поля вроде «Примечания» — не отправка, не должна
        попадать в этот специализированный журнал."""
        self._as("editor1", "editor")
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        self.client.put(f"/api/blocking-cases/{case['id']}", json={"notes": "какой-то текст"})

        self._as("admin1", "admin")
        log = self.client.get("/api/complaint-send-log").get_json()
        self.assertEqual(log, [])


if __name__ == "__main__":
    unittest.main()
