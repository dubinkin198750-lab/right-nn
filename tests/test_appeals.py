"""Тесты обновления 23.09: обращения МГС/РКН списком, распознавание
заглушек о блокировке, «ложная тревога» и возврат из архива."""
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage, link_check, jobs  # noqa: E402
from backend import appeals  # noqa: E402


class TestParsing(unittest.TestCase):
    def test_parse_date_and_number(self):
        self.assertEqual(appeals.parse_ruling_text("04.08 2И-6684", 2026), ("2026-08-04", "2И-6684"))

    def test_parse_full_year(self):
        self.assertEqual(appeals.parse_ruling_text("25.08.2026 2И-7238"), ("2026-08-25", "2И-7238"))

    def test_parse_with_number_sign(self):
        self.assertEqual(appeals.parse_ruling_text("30.07 № 2И-6626", 2026), ("2026-07-30", "2И-6626"))

    def test_unparseable_kept_as_is(self):
        self.assertEqual(appeals.parse_ruling_text("2И-6684"), ("", "2И-6684"))

    def test_invalid_date_kept_as_is(self):
        self.assertEqual(appeals.parse_ruling_text("31.02 2И-1", 2026), ("", "31.02 2И-1"))


class TestDeriveAndMirror(unittest.TestCase):
    def test_derive_from_legacy_two_appeals(self):
        case = {
            "court_ruling_number": "04.08 2И-6684", "rkn_number": "2026-08-07-5", "rkn_filed_at": "2026-08-07",
            "first_appeal_decision": "нет реакции", "repeat_ruling": "25.08 2И-7238",
            "repeat_rkn_filed_at": "2026-08-28", "repeat_appeal_decision": "",
        }
        result = appeals.get_appeals(case)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["mgs_date"], "2026-08-04")
        self.assertEqual(result[0]["mgs_number"], "2И-6684")
        self.assertEqual(result[1]["mgs_number"], "2И-7238")
        self.assertEqual(result[1]["rkn_date"], "2026-08-28")

    def test_empty_case_has_no_appeals(self):
        self.assertEqual(appeals.get_appeals({}), [])

    def test_mirror_keeps_old_fields_in_sync(self):
        lst = [
            {"mgs_date": "2026-08-04", "mgs_number": "2И-1", "rkn_date": "2026-08-07", "rkn_number": "R1", "decision": "отклонено"},
            {"mgs_date": "2026-08-25", "mgs_number": "2И-2", "rkn_date": "2026-08-28", "rkn_number": "R2", "decision": "нет реакции"},
            {"mgs_date": "2026-09-10", "mgs_number": "2И-3", "rkn_date": "2026-09-12", "rkn_number": "R3", "decision": "заблокировано"},
        ]
        m = appeals.legacy_mirror(lst)
        self.assertEqual(m["court_ruling_number"], "2И-1")
        self.assertEqual(m["first_appeal_decision"], "отклонено")
        self.assertEqual(m["repeat_appeal_decision"], "заблокировано")
        self.assertEqual(m["repeat_rkn_filed_at"], "2026-09-12")
        self.assertIn("2И-2", m["repeat_ruling"])
        self.assertIn("2И-3", m["repeat_ruling"])


class TestCurrentState(unittest.TestCase):
    def test_last_stage_decides(self):
        """Первое обращение дало «заблокировано», ссылка ожила, подано
        второе — дело больше не считается заблокированным."""
        case = {"appeals": [
            {"mgs_date": "2026-08-04", "decision": "заблокировано"},
            {"mgs_date": "2026-09-10", "decision": ""},
        ]}
        self.assertFalse(appeals.is_blocked(case))

    def test_empty_new_appeal_does_not_hide_previous(self):
        case = {"appeals": [{"mgs_date": "2026-08-04", "decision": "заблокировано"}, {}]}
        self.assertTrue(appeals.is_blocked(case))

    def test_claim_blocked_without_appeals(self):
        self.assertTrue(appeals.is_blocked({"claim_decision": "заблокировано"}))

    def test_failed_last_appeal(self):
        case = {"appeals": [{"rkn_date": "2026-08-04", "decision": "отклонено"}]}
        self.assertTrue(link_check.appeal_failed(case))


class TestStubDetection(unittest.TestCase):
    def setUp(self):
        self._orig = link_check.RETRY_DELAY_SEC
        link_check.RETRY_DELAY_SEC = 0

    def tearDown(self):
        link_check.RETRY_DELAY_SEC = self._orig

    def _resp(self, code=200, url="https://s66.zapret.me/x", text=""):
        return MagicMock(status_code=code, url=url, text=text)

    def test_provider_stub_text_is_unavailable(self):
        page = "<title>Доступ ограничен</title> Доступ к информационному ресурсу ограничен на основании 149-ФЗ"
        details = {}
        with patch("requests.get", return_value=self._resp(text=page)) as g:
            status, _ = link_check.check("https://s66.zapret.me/x", details)
        self.assertEqual(status, "недоступна")
        self.assertTrue(details["stub"])
        self.assertEqual(g.call_count, 1)  # заглушка — повторять незачем

    def test_redirect_to_stub_host_is_unavailable(self):
        with patch("requests.get", return_value=self._resp(url="http://warning.rt.ru/?id=1")):
            status, _ = link_check.check("https://s66.zapret.me/x")
        self.assertEqual(status, "недоступна")

    def test_host_containing_word_blocked_is_not_stub(self):
        with patch("requests.get", return_value=self._resp(url="https://unblocked.site/x", text="<title>Курс</title>")):
            status, _ = link_check.check("https://unblocked.site/x")
        self.assertEqual(status, "доступна")

    def test_details_filled(self):
        details = {}
        with patch("requests.get", return_value=self._resp(text="<title> Курс  1С </title>")):
            link_check.check("https://s66.zapret.me/x", details)
        self.assertEqual(details["http_code"], 200)
        self.assertEqual(details["title"], "Курс 1С")

    def test_proxy_used_when_configured(self):
        with patch.dict(os.environ, {"LINK_CHECK_PROXY": "http://ru-proxy:3128"}):
            with patch("requests.get", return_value=self._resp()) as g:
                link_check.check("https://x.test")
        self.assertEqual(g.call_args.kwargs["proxies"], {"http": "http://ru-proxy:3128", "https": "http://ru-proxy:3128"})

    def test_false_alarm_signature_suppresses_alert(self):
        details = {"http_code": 200, "final_url": "https://s66.zapret.me/x", "title": "Курс"}
        case = {"false_alarm_signature": link_check.signature(details)}
        p = link_check.build_update_patch(case, "доступна", time.time(), details)
        self.assertFalse(p["needs_resend"])
        self.assertEqual(p["link_status"], "недоступна")

    def test_changed_response_raises_alert_again(self):
        old = {"http_code": 200, "final_url": "https://s66.zapret.me/x", "title": "Заглушка"}
        new = {"http_code": 200, "final_url": "https://s66.zapret.me/x", "title": "Курс 1С — скачать"}
        case = {"false_alarm_signature": link_check.signature(old)}
        p = link_check.build_update_patch(case, "доступна", time.time(), new)
        self.assertTrue(p["needs_resend"])


class TestApi(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"
        self.author = storage.upsert_author({"id": None, "name": "Автор"})

    def _case(self, **kw):
        base = {"title": "т", "url": "https://s66.zapret.me/1", "author_name": "Автор"}
        base.update(kw)
        return storage.add_blocking_case(base)

    def _put(self, case_id, body):
        return self.client.put(f"/api/blocking-cases/{case_id}", json=body)

    def test_save_appeals_mirrors_legacy_fields(self):
        c = self._case()
        resp = self._put(c["id"], {"appeals": [
            {"mgs_date": "2026-08-04", "mgs_number": "2И-6684", "rkn_date": "2026-08-07", "rkn_number": "R1", "decision": "нет реакции"},
        ]})
        self.assertEqual(resp.status_code, 200)
        saved = storage.get_blocking_case(c["id"])
        self.assertEqual(saved["court_ruling_number"], "2И-6684")
        self.assertEqual(saved["court_ruling_date"], "2026-08-04")
        self.assertEqual(saved["first_appeal_decision"], "нет реакции")

    def test_invalid_decision_rejected(self):
        c = self._case()
        resp = self._put(c["id"], {"appeals": [{"decision": "что-то"}]})
        self.assertEqual(resp.status_code, 400)

    def test_invalid_date_rejected(self):
        c = self._case()
        resp = self._put(c["id"], {"appeals": [{"mgs_date": "04.08.2026"}]})
        self.assertEqual(resp.status_code, 400)

    def test_blocked_in_appeal_archives(self):
        c = self._case()
        resp = self._put(c["id"], {"appeals": [{"rkn_date": "2026-09-01", "decision": "заблокировано"}]})
        self.assertTrue(resp.get_json().get("auto_archived"))

    def test_new_appeal_dates_clear_needs_resend(self):
        c = self._case(appeals=[{"rkn_date": "2026-08-01", "decision": "отклонено"}])
        storage.update_blocking_case(c["id"], {"needs_resend": True})
        self._put(c["id"], {"appeals": [
            {"rkn_date": "2026-08-01", "decision": "отклонено"},
            {"rkn_date": "2026-09-20", "decision": ""},
        ]})
        self.assertFalse(storage.get_blocking_case(c["id"])["needs_resend"])

    def test_typo_fix_does_not_clear_needs_resend(self):
        c = self._case(appeals=[{"rkn_date": "2026-08-01", "decision": "отклонено"}])
        storage.update_blocking_case(c["id"], {"needs_resend": True})
        self._put(c["id"], {"appeals": [{"rkn_date": "2026-08-02", "decision": "отклонено"}]})
        self.assertTrue(storage.get_blocking_case(c["id"])["needs_resend"])

    def test_legacy_client_fields_still_work(self):
        c = self._case()
        self._put(c["id"], {"court_ruling_number": "04.08 2И-6684", "rkn_filed_at": "2026-08-07"})
        saved = storage.get_blocking_case(c["id"])
        self.assertEqual(saved["appeals"][0]["mgs_number"], "2И-6684")
        self.assertEqual(saved["appeals"][0]["mgs_date"], "2026-08-04")
        self.assertEqual(saved["appeals"][0]["rkn_date"], "2026-08-07")

    def test_adding_empty_appeal_to_revived_case_does_not_archive(self):
        """Найдено при проверке в браузере 23.09: у заблокированного дела с
        ожившей ссылкой кнопка «+ Повторное обращение» сразу отправляла
        дело в архив."""
        c = self._case(appeals=[{"rkn_date": "2026-08-04", "decision": "заблокировано"}],
                       block_date="2026-09-10", needs_resend=True)
        resp = self._put(c["id"], {"appeals": [
            {"rkn_date": "2026-08-04", "decision": "заблокировано"}, {},
        ]})
        self.assertNotIn("auto_archived", resp.get_json())
        saved = storage.get_blocking_case(c["id"])
        self.assertTrue(saved["needs_resend"])
        self.assertEqual(saved["block_date"], "2026-09-10")

    def test_second_appeal_blocked_archives(self):
        c = self._case(appeals=[{"rkn_date": "2026-08-04", "decision": "нет реакции"}, {"rkn_date": "2026-09-01"}])
        resp = self._put(c["id"], {"appeals": [
            {"rkn_date": "2026-08-04", "decision": "нет реакции"}, {"rkn_date": "2026-09-01", "decision": "заблокировано"},
        ]})
        self.assertTrue(resp.get_json().get("auto_archived"))

    def test_confirm_blocked_archives_and_remembers_signature(self):
        """Сценарий s66.zapret.me: заблокировано, проверка «оживила»
        ссылку, сотрудник нажимает «Ложная тревога»."""
        c = self._case(claim_decision="заблокировано", block_date="2026-09-10", needs_resend=True,
                       link_check_details={"signature": "200|s66.zapret.me/1|заглушка"})
        resp = self.client.post(f"/api/blocking-cases/{c['id']}/confirm-blocked")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["auto_archived"])
        entry = [e for e in storage.load_report_archive() if e["id"] == c["id"]][0]
        self.assertEqual(entry["false_alarm_signature"], "200|s66.zapret.me/1|заглушка")
        self.assertFalse(entry["needs_resend"])

    def test_confirm_blocked_requires_blocked_status(self):
        c = self._case(needs_resend=True)
        resp = self.client.post(f"/api/blocking-cases/{c['id']}/confirm-blocked")
        self.assertEqual(resp.status_code, 400)

    def test_archived_case_with_same_signature_not_restored(self):
        details = {"http_code": 200, "final_url": "https://s66.zapret.me/1", "title": "Курс"}
        c = self._case(claim_decision="заблокировано", block_date="2026-01-01",
                       false_alarm_signature=link_check.signature(details))
        storage.archive_reported_cases([storage.get_blocking_case(c["id"])], 2026, 1)

        def fake_check(url, d=None):
            if d is not None:
                d.update(details)
            return "доступна", time.time()

        with patch("backend.link_check.check", side_effect=fake_check):
            jobs._check_due_archived_cases_once()
        self.assertIsNone(storage.get_blocking_case(c["id"]))
        entry = [e for e in storage.load_report_archive() if e["id"] == c["id"]][0]
        self.assertEqual(entry["link_status"], "недоступна")


if __name__ == "__main__":
    unittest.main()
