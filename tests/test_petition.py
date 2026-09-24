import io
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import petition  # noqa: E402


def _extract_text(docx_bytes):
    """Достаём читаемый текст из .docx для проверки содержимого — без
    внешних зависимостей вроде pandoc, читаем XML напрямую."""
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    import re
    return " ".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))


class TestBuildPetitionDocx(unittest.TestCase):
    def setUp(self):
        self.personal = {
            "full_name": "Тестов Тест Тестович",
            "birth_place": "г. Тест",
            "passport": "11 11 111111",
            "issued_by": "ОВД Тестового района",
            "snils": "111-111-111 11",
        }

    def test_produces_valid_docx_bytes(self):
        cases = [{"url": "https://x.test/1", "work_title": "Работа"}]
        docx_bytes = petition.build_petition_docx(self.personal, "Автор Тестов", cases)
        self.assertEqual(docx_bytes[:2], b"PK")  # docx это zip-контейнер
        self.assertGreater(len(docx_bytes), 500)

    def test_includes_personal_fields(self):
        cases = [{"url": "https://x.test/1", "work_title": "Работа"}]
        docx_bytes = petition.build_petition_docx(self.personal, "Автор Тестов", cases)
        text = _extract_text(docx_bytes)
        self.assertIn("Тестов Тест Тестович", text)
        self.assertIn("11 11 111111", text)
        self.assertIn("111-111-111 11", text)

    def test_includes_full_url_of_each_case_not_just_domain(self):
        """Поведение сознательно изменено 01.09 по прямой просьбе
        пользователя (см. заметку разработки, п.7): раньше в заявление
        вставлялось только доменное имя — этого оказалось недостаточно,
        суду нужна именно точная страница с нарушением, не просто домен.
        Теперь полная ссылка есть в отдельном разделе «Ссылки на
        нарушения» — путь страницы (`threads/...`, `watch?v=...`) должен
        попадать в текст, а не вырезаться."""
        cases = [
            {"url": "https://x.test/threads/some-long-page-path-here", "work_title": "Работа А"},
            {"url": "https://y.test/watch?v=abc123", "work_title": "Работа Б"},
        ]
        docx_bytes = petition.build_petition_docx(self.personal, "Автор", cases)
        text = _extract_text(docx_bytes)
        self.assertIn("x.test", text)
        self.assertIn("y.test", text)
        self.assertIn("threads/some-long-page-path-here", text)
        self.assertIn("watch?v=abc123", text)

    def test_urls_not_duplicated_between_violations_section_and_defendants_section(self):
        """Раньше (до 03.09) полная ссылка на нарушение печаталась дважды —
        один раз в разделе «Ссылки на нарушения», второй раз ещё и
        маркированным списком под доменом в разделе «Ответчики»
        (см. заметку разработки, п.7). Каждая ссылка должна встречаться в
        итоговом документе ровно один раз, не два."""
        cases = [
            {"url": "https://x.test/only-once-here", "work_title": "Работа", "defendant": "Cloudflare"},
        ]
        docx_bytes = petition.build_petition_docx(self.personal, "Автор", cases)
        text = _extract_text(docx_bytes)
        self.assertEqual(text.count("only-once-here"), 1)

    def test_duplicate_case_produces_one_defendant_line_not_two(self):
        """Раздел «Ответчики» группирует дела по домену — если у двух дел
        один и тот же домен и один и тот же ответчик, строка с описанием
        ответчика (имя, IP, адрес) должна быть только одна, не по одной на
        каждое дело. Полные ссылки при этом перечисляются под этой строкой
        по одной на каждое дело — то есть не задвоены сами ссылки (их две,
        как и должно быть, раз дел два), задвоена не должна быть только
        строка с данными ответчика."""
        cases = [
            {"url": "https://x.test/dup-a", "work_title": "Работа", "defendant": "Cloudflare"},
            {"url": "https://x.test/dup-b", "work_title": "Работа", "defendant": "Cloudflare"},
        ]
        docx_bytes = petition.build_petition_docx(self.personal, "Автор", cases)
        text = _extract_text(docx_bytes)
        # Имя ответчика законно встречается дважды: один раз в самом
        # «Требовании» (там теперь настоящий ответчик вместо старой
        # заглушки-плейсхолдера — отдельное сегодняшнее исправление, см.
        # заметку разработки, п.6), и один раз в разделе «Ответчики» с
        # IP/адресом. А вот САМА строка в «Ответчики» не должна быть
        # задвоена на 2 дела с одинаковым доменом — проверяем именно её
        # отдельно, по характерному "(IP:", которого нет в «Требовании».
        self.assertEqual(text.count("Cloudflare"), 2)
        self.assertEqual(text.count("Cloudflare (IP:"), 1)  # строка в «Ответчики» — не задвоена
        self.assertIn("dup-a", text)  # обе ссылки при этом на месте
        self.assertIn("dup-b", text)

    def test_missing_personal_field_shown_as_placeholder_not_empty(self):
        incomplete = dict(self.personal)
        del incomplete["passport"]
        cases = [{"url": "https://x.test/1", "work_title": "Работа"}]
        docx_bytes = petition.build_petition_docx(incomplete, "Автор", cases)
        text = _extract_text(docx_bytes)
        self.assertIn("[не указано]", text)  # явная пометка, а не молчаливый пропуск

    def test_missing_defendant_flagged_for_manual_fill(self):
        cases = [{"url": "https://x.test/1", "work_title": "Работа", "defendant": "", "ip_address": ""}]
        docx_bytes = petition.build_petition_docx(self.personal, "Автор", cases)
        text = _extract_text(docx_bytes)
        self.assertIn("[указать наименование ответчика]", text)

    def test_defendant_address_included_when_filled(self):
        cases = [{
            "url": "https://x.test/1", "work_title": "Работа", "defendant": "Cloudflare, Inc.",
            "defendant_address": "101 Townsend St, San Francisco, CA 94107, USA",
        }]
        docx_bytes = petition.build_petition_docx(self.personal, "Автор", cases)
        text = _extract_text(docx_bytes)
        self.assertIn("101 Townsend St", text)

    def test_defendant_address_placeholder_when_empty(self):
        cases = [{"url": "https://x.test/1", "work_title": "Работа", "defendant": "Cloudflare"}]
        docx_bytes = petition.build_petition_docx(self.personal, "Автор", cases)
        text = _extract_text(docx_bytes)
        self.assertIn("[указать адрес регистрации]", text)


class TestBuildPetitionDocxEntityType(unittest.TestCase):
    """entity_type в личных данных автора определяет, какой раздел
    попадает в заявление — см. author_personal_data.py FIELDS."""

    def _cases(self):
        return [{"url": "https://x.test/1", "work_title": "Работа"}]

    def test_individual_shows_personal_fields_not_organization(self):
        personal = {"entity_type": "individual", "full_name": "Иванов Иван Иванович", "passport": "11 11 111111"}
        text = _extract_text(petition.build_petition_docx(personal, "Автор", self._cases()))
        self.assertIn("Физическое лицо", text)
        self.assertIn("Иванов Иван Иванович", text)
        self.assertNotIn("Юридическое лицо", text)

    def test_organization_shows_org_fields_not_personal(self):
        """Ключевая суть запроса: для юрлица — реквизиты организации, БЕЗ
        паспорта и адреса регистрации физлица."""
        personal = {
            "entity_type": "organization", "org_name": "ООО «Правообладатель»",
            "org_inn": "7700000000", "org_kpp": "770000000", "org_address": "г. Москва, ул. Тестовая, д. 1",
            "org_representative": "Петров Пётр Петрович",
            "passport": "не должно попасть в документ",
        }
        text = _extract_text(petition.build_petition_docx(personal, "Автор", self._cases()))
        self.assertIn("Юридическое лицо", text)
        self.assertIn("ООО «Правообладатель»", text)
        self.assertIn("7700000000", text)
        self.assertIn("Петров Пётр Петрович", text)
        self.assertNotIn("Физическое лицо", text)
        self.assertNotIn("Паспорт", text)
        self.assertNotIn("не должно попасть в документ", text)

    def test_individual_entrepreneur_shows_own_heading_with_org_fields(self):
        """ИП — используются те же поля, что и у юрлица, но заголовок
        раздела в заявлении должен явно отличаться от «Юридическое лицо»."""
        personal = {
            "entity_type": "individual_entrepreneur", "org_name": "ИП Иванов Иван Иванович",
            "org_inn": "770000000000", "org_address": "г. Москва, ул. Тестовая, д. 1",
        }
        text = _extract_text(petition.build_petition_docx(personal, "Автор", self._cases()))
        self.assertIn("Индивидуальный предприниматель", text)
        self.assertIn("ИП Иванов Иван Иванович", text)
        self.assertIn("770000000000", text)
        self.assertNotIn("Юридическое лицо", text)
        self.assertNotIn("Физическое лицо", text)

    def test_missing_entity_type_defaults_to_individual(self):
        """Обратная совместимость: у уже сохранённых записей (до появления
        этого поля) entity_type не проставлен вовсе — должны по-прежнему
        показывать раздел «Физическое лицо»."""
        personal = {"full_name": "Старая запись без entity_type"}
        text = _extract_text(petition.build_petition_docx(personal, "Автор", self._cases()))
        self.assertIn("Физическое лицо", text)


class TestBuildPetitionDocxAttachmentsSection(unittest.TestCase):
    def setUp(self):
        self.personal = {"full_name": "Тестов Тест Тестович"}
        self.cases = [{"url": "https://x.test/1", "work_title": "Работа"}]

    def test_no_totals_line_even_with_attachments(self):
        """Строка "Всего приложений: N файлов" убрана по прямой просьбе
        пользователя (см. заметку разработки, 03.09) — постатейная
        разбивка достаточна сама по себе."""
        counts = {"violation_screenshots": 2, "ip_screenshots": 1}
        text = _extract_text(petition.build_petition_docx(self.personal, "Автор", self.cases, counts))
        self.assertNotIn("Всего приложений", text)

    def test_itemized_breakdown_still_present(self):
        """Убрали только итоговую строку — постатейная разбивка (по
        каждому типу документа отдельно) остаётся, как и раньше."""
        counts = {"violation_screenshots": 3}
        text = _extract_text(petition.build_petition_docx(self.personal, "Автор", self.cases, counts))
        self.assertIn("3 файла", text)

    def test_no_attachments_section_at_all_when_counts_empty(self):
        text = _extract_text(petition.build_petition_docx(self.personal, "Автор", self.cases, None))
        self.assertNotIn("Приложения", text)
        self.assertNotIn("Всего приложений", text)


if __name__ == "__main__":
    unittest.main()
