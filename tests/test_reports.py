import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import reports  # noqa: E402


def case(**kw):
    base = {
        "author_name": "Автор", "work_title": "Произведение", "url": "https://x.test/1",
        "title": "т", "claim_decision": "", "first_appeal_decision": "", "repeat_appeal_decision": "",
        "claim_date": "", "court_ruling_date": "",
        "block_date": "", "court_ruling_number": "", "repeat_ruling": "", "rkn_number": "",
        "needs_resend": False,
    }
    base.update(kw)
    return base


class TestCasesForMonth(unittest.TestCase):
    def test_matches_by_claim_date(self):
        cases = [case(first_appeal_decision="заблокировано", claim_date="2026-08-05")]
        result = reports.cases_for_month(cases, 2026, 8)
        self.assertEqual(len(result), 1)

    def test_matches_by_court_ruling_date(self):
        cases = [case(first_appeal_decision="заблокировано", court_ruling_date="2026-08-12")]
        result = reports.cases_for_month(cases, 2026, 8)
        self.assertEqual(len(result), 1)

    def test_matches_by_block_date(self):
        cases = [case(first_appeal_decision="заблокировано", block_date="2026-08-20")]
        result = reports.cases_for_month(cases, 2026, 8)
        self.assertEqual(len(result), 1)

    def test_no_match_different_month(self):
        cases = [case(first_appeal_decision="заблокировано", claim_date="2026-07-05")]
        result = reports.cases_for_month(cases, 2026, 8)
        self.assertEqual(result, [])

    def test_empty_dates_never_match(self):
        cases = [case(first_appeal_decision="заблокировано")]
        result = reports.cases_for_month(cases, 2026, 8)
        self.assertEqual(result, [])

    def test_only_blocked_cases_included(self):
        """Ключевое поведение: отчёт показывает только дела, где хотя бы
        один из трёх этапов дал решение «заблокировано» — даже если у
        других дел есть движение в этом же месяце."""
        cases = [
            case(claim_date="2026-08-05", url="https://x.test/open"),  # ничего ещё не определено
            case(first_appeal_decision="отклонено", claim_date="2026-08-06", url="https://x.test/rejected"),
            case(first_appeal_decision="заблокировано", block_date="2026-08-08", url="https://x.test/blocked"),
        ]
        result = reports.cases_for_month(cases, 2026, 8)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["url"], "https://x.test/blocked")

    def test_needs_resend_case_still_counted_for_original_block_month(self):
        """Регрессия на пункт критики: дело заблокировали в августе, а
        позже (уже в сентябре, когда сработала фоновая проверка) ссылка
        снова ожила и needs_resend встал сам — отчёт за август всё равно
        должен показать этот факт блокировки, а не потерять дело только
        из-за того, что needs_resend на момент отчёта уже True."""
        cases = [case(
            first_appeal_decision="заблокировано", needs_resend=True,
            block_date="2026-08-08", url="https://x.test/repeat",
        )]
        result = reports.cases_for_month(cases, 2026, 8)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["url"], "https://x.test/repeat")

    def test_blocked_via_claim_stage_alone_is_included(self):
        """Блокировка могла случиться уже на этапе досудебной претензии,
        не дойдя до суда/РКН вообще — это тоже is_blocked()."""
        cases = [case(claim_decision="заблокировано", block_date="2026-08-08", url="https://x.test/claim-only")]
        result = reports.cases_for_month(cases, 2026, 8)
        self.assertEqual(len(result), 1)

    def test_blocked_via_repeat_stage_alone_is_included(self):
        cases = [case(repeat_appeal_decision="заблокировано", block_date="2026-08-08", url="https://x.test/repeat-only")]
        result = reports.cases_for_month(cases, 2026, 8)
        self.assertEqual(len(result), 1)


class TestBuildMonthlyReport(unittest.TestCase):
    def test_produces_valid_xlsx_bytes(self):
        cases = [case(first_appeal_decision="заблокировано", claim_date="2026-08-05")]
        xlsx_bytes = reports.build_monthly_report(cases, 2026, 8)
        self.assertGreater(len(xlsx_bytes), 100)
        self.assertEqual(xlsx_bytes[:2], b"PK")  # xlsx это zip-контейнер

    def test_empty_cases_does_not_crash(self):
        xlsx_bytes = reports.build_monthly_report([], 2026, 8)
        self.assertGreater(len(xlsx_bytes), 100)

    def test_non_blocked_cases_excluded_from_report(self):
        import openpyxl
        import io
        cases = [case(claim_date="2026-08-05", url="https://x.test/should-not-appear")]  # ничего не заблокировано
        xlsx_bytes = reports.build_monthly_report(cases, 2026, 8)
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
        ws = wb.active
        found = any(
            cell == "https://x.test/should-not-appear"
            for row in ws.iter_rows(values_only=True) for cell in row
        )
        self.assertFalse(found)


if __name__ == "__main__":
    unittest.main()
