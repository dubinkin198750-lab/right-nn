"""Тесты на то, что обращение в РКН встроено в тот же цикл автоматического
мониторинга, что и заявление в суд — по описанному пользователем процессу:
если через 14 дней после подачи (в суд ИЛИ в РКН, смотря что позже) меры
не приняты, дело нужно снова выбрать и для заявления в суд, и для
повторного обращения в РКН одновременно."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


class TestRknResendReset(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def test_new_rkn_filed_at_resets_needs_resend(self):
        """Ключевое новое поведение: новая дата подачи в РКН (после того,
        как needs_resend встал True — «меры не приняты») сбрасывает
        мониторинг точно так же, как это уже было устроено для заявления
        в суд, а не только оно одно."""
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        storage.update_blocking_case(case["id"], {
            "needs_resend": True, "link_status": "доступна", "link_checked_at": 12345,
        })

        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"rkn_filed_at": "2026-08-13"})
        updated = resp.get_json()
        self.assertFalse(updated["needs_resend"])
        self.assertEqual(updated["link_status"], "")
        self.assertEqual(updated["link_checked_at"], "")

    def test_new_repeat_petition_date_resets_needs_resend(self):
        """Дата ПОВТОРНОЙ подачи в суд (отдельное поле от первой) —
        тоже должна сбрасывать мониторинг."""
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        storage.update_blocking_case(case["id"], {
            "needs_resend": True, "link_status": "доступна", "link_checked_at": 12345,
        })
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"repeat_petition_filed_at": "2026-08-13"})
        updated = resp.get_json()
        self.assertFalse(updated["needs_resend"])

    def test_new_repeat_rkn_date_resets_needs_resend(self):
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        storage.update_blocking_case(case["id"], {
            "needs_resend": True, "link_status": "доступна", "link_checked_at": 12345,
        })
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"repeat_rkn_filed_at": "2026-08-13"})
        updated = resp.get_json()
        self.assertFalse(updated["needs_resend"])

    def test_first_and_repeat_filing_dates_are_independent_fields(self):
        """Ключевая суть запроса — первая и повторная подача хранятся
        раздельно, повторная не затирает первую."""
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        storage.update_blocking_case(case["id"], {
            "petition_filed_at": "2026-06-01", "rkn_filed_at": "2026-06-05",
        })
        storage.update_blocking_case(case["id"], {
            "repeat_petition_filed_at": "2026-08-01", "repeat_rkn_filed_at": "2026-08-05",
        })
        updated = storage.get_blocking_case(case["id"])
        self.assertEqual(updated["petition_filed_at"], "2026-06-01")  # первая дата не тронута
        self.assertEqual(updated["rkn_filed_at"], "2026-06-05")
        self.assertEqual(updated["repeat_petition_filed_at"], "2026-08-01")
        self.assertEqual(updated["repeat_rkn_filed_at"], "2026-08-05")

    def test_google_dmca_filed_at_is_a_plain_manual_date_field(self):
        """Дата отправки жалобы в Google DMCA — простое ручное поле, без
        автоматического заполнения формы (решили не делать автоматизацию
        входа в Google-аккаунт — риск блокировки аккаунта и юридический
        риск автоматической отправки документа с подписью)."""
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"google_dmca_filed_at": "2026-08-14"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["google_dmca_filed_at"], "2026-08-14")

    def test_editing_rkn_date_without_needs_resend_does_not_reset_monitoring(self):
        """Просто поправили опечатку в уже стоявшей дате РКН — needs_resend
        в этот момент False (дело не помечено как требующее повтора), не
        должно ничего сбрасывать, только правит саму дату."""
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        storage.update_blocking_case(case["id"], {
            "rkn_filed_at": "2026-08-01", "needs_resend": False,
            "link_status": "недоступна", "link_checked_at": 12345,
        })

        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"rkn_filed_at": "2026-08-02"})
        updated = resp.get_json()
        self.assertEqual(updated["link_status"], "недоступна")  # не сброшено
        self.assertEqual(updated["link_checked_at"], 12345)  # не сброшено
        self.assertEqual(updated["rkn_filed_at"], "2026-08-02")  # дата всё же поправилась

    def test_full_cycle_petition_then_rkn_then_no_response_flags_both(self):
        """Полный сценарий по описанному пользователем процессу: подали
        заявление в суд → позже подали в РКН → 14 дней с более поздней
        (РКН) даты без реакции → needs_resend встаёт, дело снова доступно
        для выбора и на повторное заявление, и на повторное обращение."""
        from backend import link_check
        import time

        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        petition_date = time.strftime("%Y-%m-%d", time.localtime(time.time() - 20 * 86400))
        rkn_date = time.strftime("%Y-%m-%d", time.localtime(time.time() - 15 * 86400))
        storage.update_blocking_case(case["id"], {
            "petition_filed_at": petition_date, "rkn_filed_at": rkn_date,
        })
        updated_case = storage.get_blocking_case(case["id"])

        self.assertTrue(link_check.is_due(updated_case))  # 15 дней с РКН — уже пора проверять

        patch = link_check.build_update_patch(updated_case, "доступна", time.time())
        self.assertTrue(patch["needs_resend"])  # ссылка всё ещё доступна — обе подачи не подействовали

    def test_first_appeal_decision_accepts_only_fixed_values(self):
        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"first_appeal_decision": "какой-то произвольный текст"})
        self.assertEqual(resp.status_code, 400)

    def test_first_appeal_decision_accepts_each_valid_value(self):
        """«заблокировано» на СВЕЖЕМ деле теперь мгновенно архивирует его
        (см. заметку разработки, п. «Вариант 2» от 01.09) — дальше этот
        же case_id уже недоступен для PUT напрямую (нужно сперва
        восстановить из архива). Раньше тест проверял все 4 значения
        подряд на ОДНОМ деле — теперь «заблокировано» проверяем отдельно
        (на своём одноразовом деле), а последовательность остальных трёх
        (которые не архивируют) — на другом деле, как и раньше."""
        blocked_case = storage.add_blocking_case({"title": "т", "url": "https://x.test/1", "author_name": "А"})
        resp = self.client.put(f"/api/blocking-cases/{blocked_case['id']}", json={"first_appeal_decision": "заблокировано"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["first_appeal_decision"], "заблокировано")
        self.assertTrue(resp.get_json().get("auto_archived"))

        case = storage.add_blocking_case({"title": "т", "url": "https://x.test/2", "author_name": "А"})
        for decision in ("отклонено", "нет реакции", ""):
            resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={"first_appeal_decision": decision})
            self.assertEqual(resp.status_code, 200, f"не принял валидное значение {decision!r}")
            self.assertEqual(resp.get_json()["first_appeal_decision"], decision)

    def test_first_appeal_decision_blocked_but_link_still_up_triggers_repeat_via_background_monitor(self):
        """Сквозная проверка через реальный фоновый цикл мониторинга (не
        напрямую функции link_check) — решение «заблокировано» по первому
        обращению + ссылка реально доступна → needs_resend встаёт, точно
        как описано в процессе пользователя. Общего поля «Статус» больше
        нет — само решение (first_appeal_decision) остаётся как было,
        какое из трёх решений поправить дальше, решает сотрудник вручную.

        Раньше здесь проверялась ручная кнопка «Проверить сейчас»
        (/check-link) — но с мгновенной архивацией «заблокировано» (см.
        заметку разработки, «Вариант 2» от 01.09) дело сразу уходит в
        архив, и эта кнопка для него больше не показывается (её нет ни у
        одной архивной записи в интерфейсе). Мониторинг для таких дел
        теперь целиком фоновый — см. jobs._check_due_cases_once, которая
        проверяет и активные, и заархивированные дела в одном проходе, и
        сама возвращает дело в «Блокировку», если ссылка снова ожила —
        именно эту функцию и вызываем здесь напрямую."""
        import time
        from unittest.mock import patch as mock_patch
        from backend import jobs

        case = storage.add_blocking_case({
            "title": "т", "url": "https://x.test/1", "author_name": "А",
        })
        create_resp = self.client.put(f"/api/blocking-cases/{case['id']}", json={
            "first_appeal_decision": "заблокировано",
            "block_date": time.strftime("%Y-%m-%d", time.localtime(time.time() - 20 * 86400)),
        })
        self.assertTrue(create_resp.get_json().get("auto_archived"))
        self.assertIsNone(storage.get_blocking_case(case["id"]))  # ушло в архив сразу

        with mock_patch("backend.link_check.check", return_value=("доступна", time.time())):
            jobs._check_due_cases_once()

        updated = storage.get_blocking_case(case["id"])
        self.assertIsNotNone(updated, "дело не вернулось из архива в «Блокировку», хотя ссылка снова доступна")
        self.assertTrue(updated["needs_resend"])
        self.assertEqual(updated["first_appeal_decision"], "заблокировано")  # само решение не подменяется автоматически


if __name__ == "__main__":
    unittest.main()
