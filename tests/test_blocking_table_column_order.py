"""Тест на реальную найденную уязвимость: заголовок таблицы «Блокировка»
(frontend/index.html) и порядок ячеек в JS-рендере строки
(frontend/app.js, renderBlockingRow) — два разных файла, синхронизируются
вручную, никакой автоматической связи между ними нет. Колонки уже
несколько раз переставлялись по ходу разработки — если в какой-то момент
порядок в одном файле разъедется с другим, таблица начнёт тихо показывать
данные не под теми заголовками, без единой ошибки где-либо (это чистый
текст, не выполняется никаким JS-движком в тестах — рассинхронизация не
бросит исключение, просто будет неверно отображаться).

Тест не выполняет JS — сверяет порядок текстовых маркеров в исходном коде,
этого достаточно, чтобы поймать «переставили одно, забыли другое»."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INDEX_HTML = os.path.join(_PROJECT_ROOT, "frontend", "index.html")
_APP_JS = os.path.join(_PROJECT_ROOT, "frontend", "app.js")

# Ожидаемый порядок: (текст заголовка в <th>, маркер — уникальная подстрока,
# которая должна встречаться в JS-шаблоне строки renderBlockingRow именно
# в ЭТОЙ ячейке, раньше по тексту, чем маркер следующей). Первая и
# последняя колонки — пустой заголовок (чекбокс выбора и кнопка «Удалить»
# соответственно), их тоже проверяем — по маркеру, не по тексту.
EXPECTED_COLUMNS = [
    ("", 'class="blocking-select-cb"'),
    ("Дата обнаружения", 'data-field="discovered_at"'),
    ("Произведение", "escapeHtml(who)"),
    ("Ссылка", 'class="r-title"'),
    ("В выдаче", 'class="presence-cell"'),
    ("Ответчик", 'data-field="defendant"'),
    ("Адрес ответчика", 'data-field="defendant_address"'),
    ("IP-адрес", 'class="ip-cell"'),
    ("Скриншоты", 'data-act="shots"'),
    ("Email ответчика", 'class="email-cell"'),
    ("Дата претензии", 'data-field="claim_date"'),
    ("Решение по претензии", 'data-field="claim_decision"'),
    ("Жалобы", 'data-act="other-complaints"'),
    ("Обращения: МГС (дата определения, №) → РКН (дата, №) → статус", "renderAppealsCell(c, resolvedAtClaim)"),
    ("Примечания", 'data-field="notes"'),
    ("", 'data-act="del"'),
]


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _extract_blocking_table_headers(html):
    match = re.search(r'<table class="results-table blocking-table">.*?<thead>(.*?)</thead>', html, re.S)
    if not match:
        raise AssertionError("Не нашёл <thead> таблицы блокировки в index.html — разметка сильно изменилась?")
    # <th> для "Произведение"/"Ссылка" несёт класс и вложенную ручку
    # изменения ширины (<span class="col-resize-handle">...) — для
    # сравнения важен только видимый текст заголовка, обрезаем по первому
    # вложенному тегу (у остальных <th> без вложенных тегов это просто
    # отдаёт исходный текст без изменений).
    raw_cells = re.findall(r"<th[^>]*>(.*?)</th>", match.group(1), re.S)
    return [re.split(r"<", cell, maxsplit=1)[0] for cell in raw_cells]


def _extract_render_blocking_row_body(js):
    start = js.find("function renderBlockingRow(c) {")
    if start == -1:
        raise AssertionError("Не нашёл функцию renderBlockingRow в app.js — переименовали?")
    # реальная граница конца шаблона строки — следующая строка кода сразу
    # после закрывающего tr.innerHTML = `...`; фиксированное число символов
    # раньше уже подводило (шаблон вырос, окно оказалось слишком узким и
    # обрезало часть ячеек, тест ловил ложные "не найдено")
    end_marker = 'tr.querySelectorAll("input, select, textarea")'
    end = js.find(end_marker, start)
    if end == -1:
        raise AssertionError(
            "Не нашёл конец шаблона renderBlockingRow (ищу маркер "
            f"{end_marker!r} после начала функции) — структура кода изменилась?"
        )
    return js[start:end]


class TestBlockingTableColumnOrder(unittest.TestCase):
    def setUp(self):
        self.html = _read(_INDEX_HTML)
        self.js = _read(_APP_JS)

    def test_header_count_matches_expected(self):
        headers = _extract_blocking_table_headers(self.html)
        self.assertEqual(
            len(headers), len(EXPECTED_COLUMNS),
            f"Число колонок в заголовке ({len(headers)}) не совпадает с ожидаемым "
            f"({len(EXPECTED_COLUMNS)}) — кто-то добавил/убрал колонку, не обновив этот тест "
            f"(или забыл обновить второй файл — начните разбор именно отсюда)."
        )

    def test_header_labels_match_expected_in_order(self):
        headers = _extract_blocking_table_headers(self.html)
        expected_labels = [label for label, _marker in EXPECTED_COLUMNS]
        self.assertEqual(
            headers, expected_labels,
            "Порядок или текст заголовков в index.html не совпадает с ожидаемым — "
            "см. EXPECTED_COLUMNS в этом тесте и сверьте с реальной разметкой."
        )

    def test_row_markers_appear_in_the_same_order_as_headers(self):
        """Ключевая проверка: маркеры ячеек в JS-шаблоне должны идти в ТОЙ
        ЖЕ последовательности, что и заголовки в HTML — именно это ловит
        рассинхронизацию, если кто-то переставил <td> в одном файле, забыв
        про <th> в другом (или наоборот)."""
        body = _extract_render_blocking_row_body(self.js)
        positions = []
        for label, marker in EXPECTED_COLUMNS:
            idx = body.find(marker)
            self.assertNotEqual(
                idx, -1,
                f"Маркер {marker!r} (колонка «{label}») не найден в renderBlockingRow — "
                f"разметку ячейки переписали так, что тест её больше не узнаёт? "
                f"Обновите маркер в EXPECTED_COLUMNS, если структура ячейки правда изменилась."
            )
            positions.append((label, marker, idx))

        for i in range(1, len(positions)):
            prev_label, prev_marker, prev_idx = positions[i - 1]
            cur_label, cur_marker, cur_idx = positions[i]
            self.assertLess(
                prev_idx, cur_idx,
                f"Порядок ячеек разъехался с порядком заголовков: «{cur_label}» "
                f"({cur_marker}) встречается в JS РАНЬШЕ, чем «{prev_label}» ({prev_marker}), "
                f"хотя в заголовке — наоборот. Таблица будет показывать данные не под теми колонками."
            )


if __name__ == "__main__":
    unittest.main()
