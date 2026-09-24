"""Тесты шаблона текста жалобы (/api/settings/complaint-template) и его
использования при генерации письма (/api/blocking-cases/<id>/complaint-email).
Ключевая идея по запросу пользователя: меняется только то, что относится
к конкретной ссылке ({url}, {author}, {work_title}, {ip}), весь остальной
текст — ровно тот, что задан в шаблоне, одинаковый для всех писем."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._helpers import IsolatedStorageTestCase  # noqa: E402
from backend import storage  # noqa: E402


class TestComplaintTemplateStorage(IsolatedStorageTestCase):
    def test_default_template_used_when_nothing_saved(self):
        template = storage.get_complaint_template()
        self.assertFalse(template["is_custom"])
        self.assertIn("{url}", template["body"])
        self.assertIn("{work_title}", template["subject"])

    def test_saved_template_is_returned_after_save(self):
        storage.save_complaint_template("Моя тема {work_title}", "Мой текст про {url}")
        template = storage.get_complaint_template()
        self.assertTrue(template["is_custom"])
        self.assertEqual(template["subject"], "Моя тема {work_title}")
        self.assertEqual(template["body"], "Мой текст про {url}")

    def test_reset_returns_to_default(self):
        storage.save_complaint_template("Тема", "Текст")
        storage.reset_complaint_template()
        template = storage.get_complaint_template()
        self.assertFalse(template["is_custom"])
        self.assertEqual(template["body"], storage.DEFAULT_COMPLAINT_TEMPLATE["body"])

    def test_render_substitutes_only_the_placeholders(self):
        """Ключевая проверка сути запроса — меняются только ссылки/данные
        дела, остальной текст остаётся буквально таким, как в шаблоне."""
        rendered = storage.render_complaint_template(
            "Жалоба по ссылке {url}, автор {author}, статичный текст без изменений",
            {"url": "https://pirate.test/1", "author": "Иванов И.И."},
        )
        self.assertEqual(rendered, "Жалоба по ссылке https://pirate.test/1, автор Иванов И.И., статичный текст без изменений")

    def test_render_leaves_unknown_placeholder_visible_not_crashing(self):
        """Опечатка в имени плейсхолдера — не должна ронять всё письмо."""
        rendered = storage.render_complaint_template("Текст с {опечаткой}", {"url": "x"})
        self.assertEqual(rendered, "Текст с {опечаткой}")

    def test_render_same_template_different_cases_gives_different_links(self):
        """Один и тот же шаблон, две разные ссылки — меняется именно и
        только ссылка, остальное идентично."""
        template = "Обращение по адресу {url}, everything else identical"
        r1 = storage.render_complaint_template(template, {"url": "https://a.test"})
        r2 = storage.render_complaint_template(template, {"url": "https://b.test"})
        self.assertNotEqual(r1, r2)
        self.assertIn("https://a.test", r1)
        self.assertIn("https://b.test", r2)
        # остальной текст (после подстановки) должен совпадать
        self.assertEqual(r1.replace("https://a.test", "X"), r2.replace("https://b.test", "X"))


class TestComplaintTemplateEndpoints(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        from backend import auth
        storage.create_user("editor1", auth.hash_password("x" * 10), "editor")
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def test_get_returns_default_initially(self):
        resp = self.client.get("/api/settings/complaint-template")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.get_json()["is_custom"])

    def test_put_saves_custom_template(self):
        resp = self.client.put("/api/settings/complaint-template", json={"subject": "Тема", "body": "Текст {url}"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["is_custom"])

        again = self.client.get("/api/settings/complaint-template").get_json()
        self.assertEqual(again["subject"], "Тема")

    def test_put_rejects_empty_subject_or_body(self):
        resp = self.client.put("/api/settings/complaint-template", json={"subject": "", "body": "Текст"})
        self.assertEqual(resp.status_code, 400)

    def test_put_rejects_too_long_subject(self):
        """Регрессия на найденную несостыковку: раньше не было вообще
        никакого верхнего предела длины."""
        resp = self.client.put("/api/settings/complaint-template", json={"subject": "x" * 301, "body": "Текст"})
        self.assertEqual(resp.status_code, 400)

    def test_put_rejects_too_long_body(self):
        resp = self.client.put("/api/settings/complaint-template", json={"subject": "Тема", "body": "x" * 10001})
        self.assertEqual(resp.status_code, 400)

    def test_put_accepts_subject_and_body_right_at_the_limit(self):
        resp = self.client.put("/api/settings/complaint-template", json={"subject": "x" * 300, "body": "y" * 10000})
        self.assertEqual(resp.status_code, 200)

    def test_delete_resets_to_default(self):
        self.client.put("/api/settings/complaint-template", json={"subject": "Тема", "body": "Текст"})
        resp = self.client.delete("/api/settings/complaint-template")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.get_json()["is_custom"])

    def test_viewer_role_cannot_edit_template(self):
        with self.client.session_transaction() as sess:
            sess["role"] = "viewer"
        resp = self.client.put("/api/settings/complaint-template", json={"subject": "Тема", "body": "Текст"})
        self.assertEqual(resp.status_code, 403)

    def test_viewer_role_can_still_view_template(self):
        with self.client.session_transaction() as sess:
            sess["role"] = "viewer"
        resp = self.client.get("/api/settings/complaint-template")
        self.assertEqual(resp.status_code, 200)


class TestComplaintEmailDraftUsesTemplate(IsolatedStorageTestCase):
    def setUp(self):
        super().setUp()
        from backend.app import app
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "editor1"
            sess["role"] = "editor"

    def test_draft_uses_custom_template_with_case_data(self):
        storage.save_complaint_template(
            "Своя тема: {work_title}",
            "Свой текст: ссылка {url}, IP {ip}, автор {author}",
        )
        case = storage.add_blocking_case({
            "title": "т", "url": "https://pirate.test/1", "author_name": "Петров П.П.",
            "work_title": "Курс", "ip_address": "1.2.3.4", "defendant_email": "abuse@x.test",
        })

        resp = self.client.get(f"/api/blocking-cases/{case['id']}/complaint-email")
        data = resp.get_json()
        self.assertEqual(data["subject"], "Своя тема: Курс")
        self.assertIn("https://pirate.test/1", data["body"])
        self.assertIn("1.2.3.4", data["body"])
        self.assertIn("Петров П.П.", data["body"])
        self.assertEqual(data["to"], "abuse@x.test")

    def test_two_different_cases_get_different_links_same_wording(self):
        """Финальная проверка сути вопроса: два разных дела — разные
        ссылки в письме, но одинаковая, не тронутая формулировка вокруг."""
        case1 = storage.add_blocking_case({"title": "т1", "url": "https://a.test/1", "author_name": "А"})
        case2 = storage.add_blocking_case({"title": "т2", "url": "https://b.test/2", "author_name": "А"})

        draft1 = self.client.get(f"/api/blocking-cases/{case1['id']}/complaint-email").get_json()
        draft2 = self.client.get(f"/api/blocking-cases/{case2['id']}/complaint-email").get_json()

        self.assertIn("https://a.test/1", draft1["body"])
        self.assertIn("https://b.test/2", draft2["body"])
        # убираем сами ссылки — остальной текст письма должен совпасть один в один
        normalized1 = draft1["body"].replace("https://a.test/1", "LINK")
        normalized2 = draft2["body"].replace("https://b.test/2", "LINK")
        self.assertEqual(normalized1, normalized2)


if __name__ == "__main__":
    unittest.main()
