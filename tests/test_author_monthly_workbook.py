"""Тесты backend/reports.py — build_author_monthly_workbook (лист на
произведение + акт выполненных работ) и эндпоинт скачивания."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import reports  # noqa: E402


class TestRuDateHelpers(unittest.TestCase):
    def test_ru_date_formats_correctly(self):
        self.assertEqual(reports._ru_date("2026-05-26"), "26.05.2026")

    def test_ru_date_empty_returns_empty(self):
        self.assertEqual(reports._ru_date(""), "")
        self.assertEqual(reports._ru_date(None), "")

    def test_ru_date_long_formats_with_month_name(self):
        self.assertEqual(reports._ru_date_long("2024-01-24"), "24 января 2024 года")

    def test_ru_date_long_handles_december(self):
        self.assertEqual(reports._ru_date_long("2026-12-01"), "1 декабря 2026 года")


class TestWorkRowValues(unittest.TestCase):
    def test_claim_text_built_from_claim_date(self):
        values = reports._work_row_values({"claim_date": "2026-05-22"})
        self.assertIn("22.05.2026", values["claim_text"])

    def test_empty_claim_date_gives_empty_claim_text(self):
        values = reports._work_row_values({})
        self.assertEqual(values["claim_text"], "")

    def test_decision_text_includes_court_ruling_number(self):
        values = reports._work_row_values({"court_ruling_number": "2И-4749", "court_ruling_date": "2026-05-26"})
        self.assertIn("2И-4749", values["decision_text"])
        self.assertIn("26.05.2026", values["decision_text"])

    def test_rkn_text_combines_first_and_repeat(self):
        values = reports._work_row_values({
            "rkn_number": "471171", "rkn_filed_at": "2026-05-28",
            "repeat_rkn_filed_at": "2026-06-25",
        })
        self.assertIn("471171", values["rkn_text"])
        self.assertIn("28.05.2026", values["rkn_text"])
        self.assertIn("повторно", values["rkn_text"])
        self.assertIn("25.06.2026", values["rkn_text"])

    def test_rkn_text_empty_when_nothing_filed(self):
        values = reports._work_row_values({})
        self.assertEqual(values["rkn_text"], "")


class TestBuildAuthorMonthlyWorkbook(unittest.TestCase):
    def _author(self, **overrides):
        base = {
            "id": "a1", "name": "Тестовый автор",
            "customer_name": "ООО «Тест»", "customer_director": "Иванова Ивана Ивановича",
            "contract_number": "1/2026", "contract_date": "2026-01-01", "monthly_fee": "10000",
        }
        base.update(overrides)
        return base

    def test_produces_valid_xlsx_bytes(self):
        xlsx = reports.build_author_monthly_workbook(
            self._author(), [], "2026-08-01", "2026-08-31", {},
        )
        self.assertEqual(xlsx[:2], b"PK")  # xlsx это zip-контейнер
        self.assertGreater(len(xlsx), 100)

    def test_one_sheet_per_work_plus_act_sheet(self):
        works_with_cases = [
            ({"id": "w1", "title": "Курс 1"}, []),
            ({"id": "w2", "title": "Курс 2"}, []),
        ]
        xlsx = reports.build_author_monthly_workbook(self._author(), works_with_cases, "2026-08-01", "2026-08-31", {})
        import io
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(xlsx))
        self.assertIn("Курс 1", wb.sheetnames)
        self.assertIn("Курс 2", wb.sheetnames)
        self.assertIn("Акт выполненных работ", wb.sheetnames)
        self.assertEqual(len(wb.sheetnames), 3)

    def test_work_sheet_contains_case_data(self):
        works_with_cases = [
            ({"id": "w1", "title": "Курс 1"}, [
                {"url": "https://pirate.test/1", "claim_date": "2026-05-22"},
            ]),
        ]
        xlsx = reports.build_author_monthly_workbook(self._author(), works_with_cases, "2026-08-01", "2026-08-31", {})
        import io
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(xlsx))
        ws = wb["Курс 1"]
        found_url = any(
            cell == "https://pirate.test/1"
            for row in ws.iter_rows(values_only=True) for cell in row
        )
        self.assertTrue(found_url)

    def test_act_sheet_includes_customer_and_contract(self):
        xlsx = reports.build_author_monthly_workbook(
            self._author(), [], "2026-08-01", "2026-08-31",
            {"name": "Моя юрфирма"},
        )
        import io
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(xlsx))
        ws = wb["Акт выполненных работ"]
        all_text = " ".join(str(cell) for row in ws.iter_rows(values_only=True) for cell in row if cell)
        self.assertIn("ООО «Тест»", all_text)
        self.assertIn("Иванова Ивана Ивановича", all_text)
        self.assertIn("1/2026", all_text)
        self.assertIn("Моя юрфирма", all_text)
        self.assertIn("10000", all_text)

    def test_act_sheet_without_fee_shows_placeholder_not_crash(self):
        author = self._author(monthly_fee=None)
        xlsx = reports.build_author_monthly_workbook(author, [], "2026-08-01", "2026-08-31", {})
        import io
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(xlsx))
        ws = wb["Акт выполненных работ"]
        all_text = " ".join(str(cell) for row in ws.iter_rows(values_only=True) for cell in row if cell)
        self.assertIn("___ рублей", all_text)

    def test_no_works_still_produces_valid_file(self):
        xlsx = reports.build_author_monthly_workbook(self._author(), [], "2026-08-01", "2026-08-31", {})
        self.assertEqual(xlsx[:2], b"PK")

    def test_work_title_with_forbidden_excel_characters_does_not_crash(self):
        """Название листа Excel не может содержать некоторые символы —
        регрессия на реальное ограничение openpyxl."""
        works_with_cases = [({"id": "w1", "title": "Курс: часть 1/2 [демо]"}, [])]
        xlsx = reports.build_author_monthly_workbook(self._author(), works_with_cases, "2026-08-01", "2026-08-31", {})
        self.assertEqual(xlsx[:2], b"PK")

    def test_duplicate_work_titles_get_unique_sheet_names(self):
        """Два произведения с одинаковым названием — не должны схлопнуться
        в один лист (openpyxl не разрешает два листа с одним именем)."""
        works_with_cases = [
            ({"id": "w1", "title": "Курс"}, []),
            ({"id": "w2", "title": "Курс"}, []),
        ]
        xlsx = reports.build_author_monthly_workbook(self._author(), works_with_cases, "2026-08-01", "2026-08-31", {})
        import io
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(xlsx))
        # два листа с произведением + акт = 3, а не 2 (не схлопнулись в один)
        self.assertEqual(len(wb.sheetnames), 3)


if __name__ == "__main__":
    unittest.main()
