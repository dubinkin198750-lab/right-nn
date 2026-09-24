"""Помесячный отчёт по разделу «Блокировка» — выгрузка в Excel (.xlsx).

Отчёт показывает дела, у которых хотя бы один из трёх этапов (претензия /
первое обращение в МГС и РКН / повторное обращение) получил решение
«заблокировано» — link_check.is_blocked(). Факт блокировки в отчётном
месяце не перестаёт быть фактом, даже если позже (уже в другом месяце,
когда сработала фоновая проверка) ссылка снова ожила и needs_resend
встал — дело остаётся в отчёте того месяца, когда блокировка реально
произошла.
"""
import io
import os
import re
import time
from calendar import monthrange

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import link_check
from . import appeals as appeals_mod

NAVY = "0F2142"
GOLD = "B08D57"
LIGHT = "F2EEEC"

MONTHS_RU = [
    "", "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]

COLUMNS = [
    ("who", "Автор / произведение", 26),
    ("url", "Ссылка", 40),
    ("claim_date", "Дата претензии", 14),
    ("claim_decision", "Решение по претензии", 18),
    ("appeals_text", "Обращения: МГС (дата определения, №) / РКН (дата, №) / статус", 60),
    ("block_date", "Дата блокировки", 14),
    ("petition_filed_at", "Дата подачи заявления", 16),
    ("link_status", "Доступность ссылки", 16),
    ("link_checked_at", "Дата проверки ссылки", 16),
]
N_COLS = len(COLUMNS)


def _in_month(date_str, year, month):
    if not date_str:
        return False
    prefix = f"{year:04d}-{month:02d}"
    return date_str.startswith(prefix)


def cases_for_month(cases, year, month):
    """Дела, которые БЫЛИ заблокированы (link_check.is_blocked) с
    движением именно в этом месяце (дата претензии/определения/блокировки).

    Учитывает needs_resend так же, как и раньше учитывался статус
    «повторная блокировка» — если ссылка была заблокирована в этом
    месяце, а позже (уже в другом месяце, когда сработала фоновая
    проверка) снова ожила, факт блокировки в отчётном месяце всё равно
    состоялся и не должен молча пропадать из отчёта только из-за того,
    что needs_resend на момент построения отчёта уже встал."""
    result = []
    for c in cases:
        if not link_check.is_blocked(c):
            continue
        if (_in_month(c.get("claim_date"), year, month)
                or _in_month(c.get("court_ruling_date"), year, month)
                or any(_in_month(a["mgs_date"], year, month) or _in_month(a["rkn_date"], year, month)
                       for a in appeals_mod.get_appeals(c))
                or _in_month(c.get("block_date"), year, month)):
            result.append(c)
    return result


def resolve_report_period(start_day, when=None):
    """К какому отчётному периоду (год, месяц) относится момент времени
    `when` (unix-таймстамп, по умолчанию — сейчас) при заданном дне
    начала периода `start_day` (1-28) у конкретного автора.

    start_day=1 — обычный календарный месяц, ничего не меняется (день
    попадает в тот же (год, месяц), в котором он и находится).

    Для другого start_day период называется по месяцу, в котором он
    НАЧИНАЕТСЯ — например, при start_day=15: 15 сентября - 14 октября
    называется периодом "2026-09", а не "2026-10". Число до 15-го числа
    относится ещё к предыдущему периоду (15 августа - 14 сентября =
    "2026-08"), а не к календарному сентябрю."""
    when = when if when is not None else time.time()
    dt = time.localtime(when)
    year, month, day = dt.tm_year, dt.tm_mon, dt.tm_mday
    if start_day <= 1 or day >= start_day:
        return year, month
    # день ещё не дошёл до start_day этого месяца — значит, мы всё ещё в
    # периоде, начавшемся в ПРЕДЫДУЩЕМ месяце
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _format_unix_date(ts):
    if not ts:
        return ""
    return time.strftime("%d.%m.%Y", time.localtime(ts))


def _row_values(c):
    who = " — ".join(filter(None, [c.get("author_name", ""), c.get("work_title", "")])) or "—"
    return {
        "who": who,
        "url": c.get("url", ""),
        "claim_date": c.get("claim_date", ""),
        "claim_decision": c.get("claim_decision", ""),
        "appeals_text": "\n".join(appeals_mod.summary_lines(c)),
        "block_date": c.get("block_date", ""),
        "petition_filed_at": c.get("petition_filed_at", ""),
        "link_status": c.get("link_status", "") or ("ещё не проверялась" if c.get("petition_filed_at") else ""),
        "link_checked_at": _format_unix_date(c.get("link_checked_at")),
    }


def _write_section_title(ws, row, text):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=N_COLS)
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = Font(size=12, bold=True, color=NAVY)
    ws.row_dimensions[row].height = 22
    return row + 1


def _write_header(ws, row):
    for col_idx, (key, label, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=row, column=col_idx, value=label)
        cell.font = Font(bold=True, color="FFFFFF", size=10)
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    ws.row_dimensions[row].height = 30
    return row + 1


def _write_rows(ws, row, cases):
    for i, c in enumerate(cases):
        values = _row_values(c)
        fill = PatternFill("solid", fgColor=LIGHT) if i % 2 else None
        for col_idx, (key, _label, _w) in enumerate(COLUMNS, start=1):
            cell = ws.cell(row=row, column=col_idx, value=values[key])
            cell.font = Font(size=10)
            cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            if fill:
                cell.fill = fill
        row += 1
    if not cases:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=N_COLS)
        empty_cell = ws.cell(row=row, column=1, value="Ничего нет.")
        empty_cell.font = Font(italic=True, color="5A5A5A")
        row += 1
    return row


def build_monthly_report(cases, year, month):
    """Возвращает bytes готового .xlsx файла — только заблокированные дела
    с движением в выбранном месяце."""
    movement = cases_for_month(cases, year, month)
    movement.sort(key=lambda c: (c.get("author_name") or "", c.get("work_title") or ""))

    wb = Workbook()
    ws = wb.active
    ws.title = "Отчёт"

    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = 0.4
    ws.page_margins.right = 0.4
    ws.page_margins.top = 0.5
    ws.page_margins.bottom = 0.5

    month_name = MONTHS_RU[month]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=N_COLS)
    title_cell = ws.cell(row=1, column=1, value=f"Отчёт по заблокированному контенту за {month_name} {year}")
    title_cell.font = Font(size=14, bold=True, color=NAVY)
    ws.row_dimensions[1].height = 28

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=N_COLS)
    sub_cell = ws.cell(row=2, column=1, value=f"Заблокировано за месяц: {len(movement)}")
    sub_cell.font = Font(size=10, italic=True, color="5A5A5A")

    row = 4
    ws.freeze_panes = f"A{row + 1}"
    row = _write_header(ws, row)
    row = _write_rows(ws, row, movement)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write_monthly_sheet(ws, title, months, counts, overridden, extra_rows=None):
    """Один лист с таблицей «месяц → число», подсвечивая вручную
    поправленные значения другим цветом заливки — чтобы при печати/чтении
    отчёта было видно, где сработал автоматический подсчёт, а где —
    ручная поправка администратора."""
    ws["A1"] = title
    ws["A1"].font = Font(size=13, bold=True, color=NAVY)
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 16

    row = 3
    ws.cell(row=row, column=1, value="Месяц").font = Font(bold=True, color="FFFFFF")
    ws.cell(row=row, column=1).fill = PatternFill("solid", fgColor=NAVY)
    ws.cell(row=row, column=2, value="Значение").font = Font(bold=True, color="FFFFFF")
    ws.cell(row=row, column=2).fill = PatternFill("solid", fgColor=NAVY)
    row += 1

    for month, count, is_override in zip(months, counts, overridden):
        ws.cell(row=row, column=1, value=month)
        cell = ws.cell(row=row, column=2, value=count)
        if is_override:
            cell.fill = PatternFill("solid", fgColor="FDECC8")  # мягкий жёлтый — «поправлено вручную»
            cell.font = Font(bold=True)
        row += 1

    row += 1
    note = ws.cell(row=row, column=1, value="Жёлтая заливка — значение поправлено вручную (не автоматический подсчёт).")
    note.font = Font(size=9, italic=True, color="8A8A8A")
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)

    if extra_rows:
        row += 2
        for label, value in extra_rows:
            ws.cell(row=row, column=1, value=label).font = Font(bold=True)
            ws.cell(row=row, column=2, value=value)
            row += 1


def build_analytics_report(detected, blocked, dynamics):
    """Возвращает bytes готового .xlsx с тремя листами — по одному на
    каждый раздел раздела «Аналитика». Значения — уже с применёнными
    ручными поправками (вызывающий код в app.py отвечает за то, чтобы
    передать сюда именно итоговые, а не сырые автоматические числа)."""
    wb = Workbook()

    ws1 = wb.active
    ws1.title = "Обнаружено"
    _write_monthly_sheet(
        ws1, "Обнаружено новых ссылок (по месяцам)",
        detected["months"], detected["counts"], detected.get("overridden", [False] * len(detected["months"])),
        extra_rows=[("Всего за всё время", detected.get("total_all_time", ""))],
    )
    if detected.get("top_domains"):
        row = len(detected["months"]) + 8
        ws1.cell(row=row, column=1, value="Топ доменов за всё время").font = Font(bold=True, color=NAVY)
        row += 1
        for d in detected["top_domains"]:
            ws1.cell(row=row, column=1, value=d["domain"])
            ws1.cell(row=row, column=2, value=d["count"])
            row += 1

    ws2 = wb.create_sheet("Заблокировано")
    _write_monthly_sheet(
        ws2, "Реально заблокировано (по месяцам)",
        blocked["months"], blocked["counts"], blocked.get("overridden", [False] * len(blocked["months"])),
        extra_rows=[("Всего заблокировано за всё время", blocked.get("total_blocked_all_time", ""))],
    )

    ws3 = wb.create_sheet("Динамика")
    ws3["A1"] = "Обнаружение против блокировки"
    ws3["A1"].font = Font(size=13, bold=True, color=NAVY)
    ws3.column_dimensions["A"].width = 14
    ws3.column_dimensions["B"].width = 16
    ws3.column_dimensions["C"].width = 16
    row = 3
    for col, label in enumerate(["Месяц", "Обнаружено", "Заблокировано"], start=1):
        cell = ws3.cell(row=row, column=col, value=label)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=NAVY)
    row += 1
    for month, det, blk in zip(dynamics["months"], dynamics["detected_counts"], dynamics["blocked_counts"]):
        ws3.cell(row=row, column=1, value=month)
        ws3.cell(row=row, column=2, value=det)
        ws3.cell(row=row, column=3, value=blk)
        row += 1
    row += 1
    if dynamics.get("median_days_to_block") is not None:
        ws3.cell(row=row, column=1, value="Медианное число дней от обнаружения до блокировки").font = Font(bold=True)
        ws3.cell(row=row, column=2, value=dynamics["median_days_to_block"])
        row += 1
        ws3.cell(row=row, column=1, value="Дел с известной задержкой").font = Font(bold=True)
        ws3.cell(row=row, column=2, value=dynamics.get("cases_with_known_delay", 0))

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------- отчёт по автору с актом выполненных работ ----------
# По образцу реального ежемесячного отчёта юрфирмы: один лист на каждое
# произведение автора (Ссылка / Претензия / Решение / Дата блокировки /
# Повторное решение / Обращения РКН — читаемые предложения, собранные из
# структурированных полей дела) плюс отдельный лист «Акт выполненных
# работ» с реквизитами заказчика и перечнем оказанных услуг.
#
# Все обращения берутся из списка appeals (backend/appeals.py): первое
# определение МГС — в «Решение», последующие — в «Повторное решение»,
# все обращения в РКН с номерами и датами — в «Обращения Роскомнадзор».
WORK_SHEET_COLUMNS = [
    ("url", "Ссылка", 45),
    ("claim_text", "Претензия", 30),
    ("decision_text", "Решение", 42),
    ("block_date_text", "Дата блокировки", 16),
    ("repeat_ruling", "Повторное решение", 40),
    ("rkn_text", "Обращения Роскомнадзор", 40),
]

_MONTHS_GENITIVE = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def _ru_date(iso_date):
    """"2026-05-26" -> "26.05.2026". Пустая строка, если дата не задана
    или в неожиданном формате — не бросаем исключение из-за одной кривой
    записи, просто оставляем поле пустым."""
    if not iso_date:
        return ""
    parts = str(iso_date).split("-")
    if len(parts) != 3:
        return str(iso_date)
    y, m, d = parts
    return f"{d}.{m}.{y}"


def _ru_date_long(iso_date):
    """"2026-05-26" -> "26 мая 2026 года" — для текста акта."""
    if not iso_date:
        return ""
    parts = str(iso_date).split("-")
    if len(parts) != 3:
        return str(iso_date)
    y, m, d = parts
    try:
        month_name = _MONTHS_GENITIVE[int(m)]
    except (ValueError, IndexError):
        return _ru_date(iso_date)
    return f"{int(d)} {month_name} {y} года"


def _work_row_values(c):
    claim_text = f"Претензия администрации сайта от {_ru_date(c.get('claim_date'))}" if c.get("claim_date") else ""
    appeal_list = appeals_mod.get_appeals(c)

    def ruling(a):
        if not a["mgs_number"] and not a["mgs_date"]:
            return ""
        text = "Определение Московского городского суда"
        if a["mgs_number"]:
            text += f" № {a['mgs_number']}"
        if a["mgs_date"]:
            text += f" от {_ru_date(a['mgs_date'])}"
        return text

    def rkn(a, idx):
        if not a["rkn_number"] and not a["rkn_date"]:
            return ""
        prefix = "" if idx == 0 else "повторно "
        if a["rkn_number"]:
            return f"{prefix}№ {a['rkn_number']}" + (f" от {_ru_date(a['rkn_date'])}" if a["rkn_date"] else "")
        return f"{prefix}от {_ru_date(a['rkn_date'])}"

    first = appeal_list[0] if appeal_list else appeals_mod.empty_appeal()
    return {
        "url": c.get("url", ""),
        "claim_text": claim_text,
        "decision_text": ruling(first),
        "block_date_text": _ru_date(c.get("block_date")),
        "repeat_ruling": "; ".join(filter(None, (ruling(a) for a in appeal_list[1:]))),
        "rkn_text": "; ".join(filter(None, (rkn(a, i) for i, a in enumerate(appeal_list)))),
    }


def _write_work_sheet(wb, work_title, cases):
    # Имя листа Excel не может содержать некоторые символы и длиннее 31
    # символа — обрезаем и чистим, иначе openpyxl бросит исключение на
    # ровном месте у произведения с длинным/необычным названием.
    safe_title = re.sub(r'[\\/*?:\[\]]', "", work_title or "Без названия")[:31] or "Без названия"
    base_title, suffix = safe_title, 1
    while base_title in wb.sheetnames:
        suffix += 1
        base_title = f"{safe_title[:28]} ({suffix})"
    ws = wb.create_sheet(base_title)

    ws.page_setup.orientation = "landscape"
    ws.column_dimensions["A"].width = 4

    n_cols = len(WORK_SHEET_COLUMNS)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    title_cell = ws.cell(row=1, column=1, value=work_title or "Без названия")
    title_cell.font = Font(size=13, bold=True, color=NAVY)
    ws.row_dimensions[1].height = 24

    row = 3
    for col_idx, (_key, label, width) in enumerate(WORK_SHEET_COLUMNS, start=1):
        cell = ws.cell(row=row, column=col_idx, value=label)
        cell.font = Font(bold=True, color="FFFFFF", size=10)
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    ws.row_dimensions[row].height = 26
    ws.freeze_panes = f"A{row + 1}"
    row += 1

    for i, c in enumerate(cases):
        values = _work_row_values(c)
        fill = PatternFill("solid", fgColor=LIGHT) if i % 2 else None
        for col_idx, (key, _label, _w) in enumerate(WORK_SHEET_COLUMNS, start=1):
            cell = ws.cell(row=row, column=col_idx, value=values[key])
            cell.font = Font(size=10)
            cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            if fill:
                cell.fill = fill
        row += 1
    if not cases:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=n_cols)
        empty_cell = ws.cell(row=row, column=1, value="По этому произведению пока нет ссылок в мониторинге.")
        empty_cell.font = Font(italic=True, color="5A5A5A")


_ACT_SERVICES = [
    "Постоянный поиск Нелегального Контента и выявление нарушений прав Заказчика в глобальной сети интернет из перечня Защищаемого Контента;",
    "Ведение переписки с владельцами сайтов, на которых размещён Нелегальный Контент, в целях удаления с сайтов Нелегального Контента;",
    "Ведение переписки с компанией Google Inc. для удаления ссылок на Нелегальный Контент из Google Search;",
    "Ведение переписки с компанией ООО «Яндекс» для удаления ссылок на Нелегальный Контент из «Яндекс поиск»;",
    "Ведение переписки с администрацией Torrent-сетей для осуществления блокировки Нелегального Контента, расположенного в Torrent-сетях;",
    "Ведение переписки с администрацией сайтов для блокировки Нелегального Контента на интернет-сайтах;",
    "Ведение переписки с представителями Meta Inc., с целью удаления Нелегального контента и информации о полученном контрафактном контенте.",
]


def _write_act_sheet(wb, author, works, period_start, period_end, firm_letterhead):
    ws = wb.create_sheet("Акт выполненных работ")
    ws.column_dimensions["A"].width = 2
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 90

    row = 1
    letterhead_lines = [
        firm_letterhead.get("name", ""), firm_letterhead.get("email", ""),
        firm_letterhead.get("phone", ""), firm_letterhead.get("address", ""),
    ]
    for line in letterhead_lines:
        if line:
            ws.cell(row=row, column=2, value=line).font = Font(size=10)
            row += 1
    row += 1

    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
    title_cell = ws.cell(row=row, column=2, value="АКТ ВЫПОЛНЕННЫХ РАБОТ")
    title_cell.font = Font(size=13, bold=True, color=NAVY)
    title_cell.alignment = Alignment(horizontal="center")
    row += 2

    customer_line = author.get("customer_name", "") or author.get("name", "")
    if author.get("customer_director"):
        customer_line += f" в лице генерального директора {author['customer_director']}"
    contract_line = ""
    if author.get("contract_number"):
        contract_line = f"№ {author['contract_number']}"
        if author.get("contract_date"):
            contract_line += f" от «{_ru_date_long(author['contract_date'])}»"

    fields = [
        ("Заказчик:", customer_line),
        ("Договор:", contract_line),
        ("Период:", f"{_ru_date(period_start)} — {_ru_date(period_end)}"),
        ("Предмет договора:", "прекращение деятельности нелегального контента"),
    ]
    for label, value in fields:
        ws.cell(row=row, column=2, value=label).font = Font(bold=True, color="5A5A5A")
        cell = ws.cell(row=row, column=3, value=value)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        row += 1

    ws.cell(row=row, column=2, value="Наименования произведений:").font = Font(bold=True, color="5A5A5A")
    if not works:
        ws.cell(row=row, column=3, value="—")
        row += 1
    else:
        for w in works:
            ws.cell(row=row, column=3, value=f"«{w.get('title', '')}»")
            row += 1
    row += 1

    intro = (
        f"Заказчик обратился к Исполнителю с заданием прекратить противоправные действия "
        f"неустановленных лиц, нарушающих авторские права Заказчика на произведения, "
        f"указанные выше."
    )
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
    intro_cell = ws.cell(row=row, column=2, value=intro)
    intro_cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[row].height = 48
    row += 2

    ws.cell(row=row, column=2, value="Перечень работ:").font = Font(bold=True, color="5A5A5A")
    for service in _ACT_SERVICES:
        cell = ws.cell(row=row, column=3, value=service)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        row += 1
    row += 1

    fee = author.get("monthly_fee")
    fee_text = f"Общая стоимость оказанных услуг составляет {fee} рублей." if fee else "Общая стоимость оказанных услуг составляет ___ рублей."
    ws.cell(row=row, column=2, value="Стоимость:").font = Font(bold=True, color="5A5A5A")
    ws.cell(row=row, column=3, value=fee_text)
    row += 1
    ws.cell(row=row, column=3, value="Оказанные услуги удовлетворяют требованиям Заказчика. Заказчик претензий не имеет.")
    row += 1
    ws.cell(row=row, column=3, value="Настоящий акт составлен в двух экземплярах, один из которых находится у Исполнителя, второй — у Заказчика.")


def build_author_monthly_workbook(author, works_with_cases, period_start, period_end, firm_letterhead):
    """Полная книга по одному автору: лист на каждое произведение +
    отдельный лист «Акт выполненных работ». works_with_cases — список
    [(work_dict, [cases_for_this_work]), ...]."""
    wb = Workbook()
    wb.remove(wb.active)  # первый пустой лист по умолчанию — не нужен, у нас свои листы

    for work, cases in works_with_cases:
        _write_work_sheet(wb, work.get("title", ""), cases)
    if not works_with_cases:
        wb.create_sheet("Произведения")  # хотя бы один лист — иначе openpyxl не даст сохранить пустую книгу

    _write_act_sheet(wb, author, [w for w, _ in works_with_cases], period_start, period_end, firm_letterhead)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# =====================================================================
# Отчёт для заказчика по образцу «Отчет по защите ИС в сети Интернет»
# (обновление 23.09). Один построитель на все случаи: одно произведение,
# один автор (все его произведения) или все авторы вместе — за любой период
# «с … по …». Форма листов повторяет образец юрфирмы буквально:
#   • лист «"Произведение" Яндекс»: Ссылка | Претензии | Решения | Дата
#     блокировки | Повторное решение | Дата блокировки | Обращения Роскомнадзор
#   • лист «Поисковая выдача Google»: ссылка | «Обращение от ДД.ММ» | дата
#     удаления из выдачи (без строки заголовков — как в образце)
#   • лист «Акт выполненных работ»
# Прежний построитель (build_author_monthly_workbook) оставлен без изменений.
# =====================================================================
import datetime as _dt

TEMPLATE_FONT = "Times New Roman"
TEMPLATE_SIZE = 12
TEMPLATE_WORK_COLUMNS = [
    ("Ссылка", 31.3), ("Претензии", 38.7), ("Решения", 68.3), ("Дата блокировки", 20.4),
    ("Повторное решение", 68.6), ("Дата блокировки", 23.4), ("Обращения Роскомнадзор", 33.1),
]
TEMPLATE_ACT_SERVICES = [
    "Постоянный поиск Нелегального Контента и выявление нарушений прав Заказчика в глобальной сети интернет из перечня Защищаемого Контента;",
    "Ведение переписки с владельцами сайтов, на которых размещен Нелегальный Контент, в целях удаления с сайтов Нелегального Контента;",
    "Ведение переписки с компанией Google Inc. для удаления ссылок на Нелегальный Контент из Google Search;",
    "Ведение переписки с компанией ООО «Яндекс» для удаления ссылок на Нелегальный Контент из «Яндекс поиск»;",
    "Ведение переписки с администрацией Torrent-сетей для осуществления блокировки Нелегального Контента, расположенного в Torrent-сетях;",
    "Ведение переписки с ООО «ВКонтакте» для удаления Нелегального Контента с интернет-сайта VK.com;",
    "Ведение переписки с администрацией сайтов для блокировки Нелегального Контента на интернет-сайтах с возможностью непосредственного сохранения Контента в память ЭВМ;",
    "Ведение переписки с администрацией сайтов для блокировки приложений на платформах Windows, Android, iOS, содержащих Нелегальный Контент;",
    "Ведение переписки с представителями Meta Inc., с целью удаления Нелегального контента и информации о получении контрафактного контента",
]
DATE_FMT = "DD.MM.YYYY"
GREEN_FILL = PatternFill("solid", fgColor="FFADFF2F")
ACT_LINE = Side(style="thin", color="FFB4B9C5")
# Разделительные линии акта — ровно те ячейки, что в образце
ACT_BOTTOM_LINES = ["D11", "B12", "C12", "D12", "D13", "B14", "C14", "D14", "B15", "C15", "D15", "D16",
                    "B17", "B18", "B19", "B23", "B24", "B25", "C25", "B26", "C26", "B28", "B29"]
ACT_TOP_LINES = ["B13", "C13"]
DEFAULT_LETTERHEAD = ('Юридический сервис "Right-NN" \nantipiracy@right-nn.ru\n+7(831) 410-07-91\n'
                      '603006, Нижний Новгород,\nул. Варварская, д.32, оф.405')
ACT_LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "act_logo.png")


def _as_date(iso):
    try:
        return _dt.date.fromisoformat(str(iso)[:10]) if iso else None
    except ValueError:
        return None


def _dm(iso):
    d = _as_date(iso)
    return d.strftime("%d.%m") if d else ""


def _dmy(iso):
    d = _as_date(iso)
    return d.strftime("%d.%m.%Y") if d else ""


def case_event_dates(case):
    """Все даты событий дела — по ним дело относится к периоду отчёта."""
    # Дата обнаружения и добавления сюда намеренно НЕ входят: ссылка, по
    # которой ещё ничего не сделано, в отчёт заказчику не попадает.
    dates = [case.get("claim_date"), case.get("block_date"), case.get("petition_filed_at"),
             case.get("repeat_petition_filed_at"), case.get("google_dmca_filed_at")]
    for a in appeals_mod.get_appeals(case):
        dates += [a["mgs_date"], a["rkn_date"]]
    for e in case.get("other_complaints") or []:
        dates += [e.get("filed_at"), e.get("resolved_at")]
    return [d for d in (_as_date(x) for x in dates) if d]


def case_in_period(case, start, end):
    """Дело попадает в отчёт, если хоть одно его событие (претензия,
    определение, обращение в РКН, блокировка, жалоба…) — в периоде."""
    s, e = _as_date(start), _as_date(end)
    return any(s <= d <= e for d in case_event_dates(case))


def _blocking_stage(case, appeal_list):
    """Какое обращение дало блокировку: 0 — претензия или обращение №1
    (дата идёт в колонку D), 1+ — повторное (колонка F), None — не блокировано."""
    if not appeals_mod.is_blocked(case):
        return None
    for i in range(len(appeal_list) - 1, -1, -1):
        if any(appeal_list[i][k] for k in appeals_mod.APPEAL_KEYS):
            return i if appeal_list[i]["decision"] == "заблокировано" else 0
    return 0


def template_row(case):
    """Значения колонок A–G одной строки листа «… Яндекс» — в точности как в образце."""
    appeal_list = [a for a in appeals_mod.get_appeals(case) if any(a[k] for k in appeals_mod.APPEAL_KEYS)]
    first = appeal_list[0] if appeal_list else appeals_mod.empty_appeal()

    def ruling_full(a):
        if not (a["mgs_number"] or a["mgs_date"]):
            return ""
        text = "Определение Московского городского суда"
        if a["mgs_number"]:
            text += f" № {a['mgs_number']}"
        if a["mgs_date"]:
            text += f" от {_dmy(a['mgs_date'])}"
        return text

    def ruling_short(a):
        return " от ".join(p for p in (a["mgs_number"], _dmy(a["mgs_date"])) if p)

    repeats = [a for a in appeal_list[1:] if a["mgs_number"] or a["mgs_date"]]
    repeat_text = ""
    if repeats:
        repeat_text = " / ".join([ruling_full(repeats[0])] + [ruling_short(a) for a in repeats[1:]])

    rkn_parts = []
    for a in appeal_list:
        if a["rkn_number"] or a["rkn_date"]:
            rkn_parts.append(" от ".join(p for p in (a["rkn_number"], _dm(a["rkn_date"])) if p))

    stage = _blocking_stage(case, appeal_list)
    block_date = _as_date(case.get("block_date"))
    return {
        "A": case.get("url", ""),
        "B": f"Претензия администрации сайта {_dm(case.get('claim_date'))}" if case.get("claim_date") else "",
        "C": ruling_full(first),
        "D": block_date if (block_date and stage is not None and stage == 0) else None,
        "E": repeat_text,
        "F": block_date if (block_date and stage is not None and stage >= 1) else None,
        "G": "; ".join(rkn_parts),
    }


def _template_sort_key(case):
    appeal_list = appeals_mod.get_appeals(case)
    first_mgs = appeal_list[0]["mgs_date"] if appeal_list else ""
    return (case.get("claim_date") or "9999", first_mgs or "9999", case.get("url", ""))


def _tfont(bold=False, color=None):
    return Font(name=TEMPLATE_FONT, size=TEMPLATE_SIZE, bold=bold, color=color)


LABEL_GRAY = "FF969CA9"  # цвет подписей акта в образце


def _unique_sheet_title(wb, title):
    safe = re.sub(r'[\\/*?:\[\]]', "", title or "Лист")[:31] or "Лист"
    candidate, n = safe, 1
    while candidate in wb.sheetnames:
        n += 1
        candidate = f"{safe[:27]} ({n})"
    return candidate


def _write_template_work_sheet(wb, sheet_title, cases):
    ws = wb.create_sheet(_unique_sheet_title(wb, sheet_title))
    for col, (label, width) in enumerate(TEMPLATE_WORK_COLUMNS, start=1):
        ws.cell(row=1, column=col, value=label).font = _tfont()
        ws.column_dimensions[get_column_letter(col)].width = width
    rows = [template_row(c) for c in sorted(cases, key=_template_sort_key)]
    rows = [v for v in rows if any(v[k] for k in "BCDEFG")]  # ссылки без результатов в отчёт не идут
    for r, values in enumerate(rows, start=2):
        for col, key in enumerate("ABCDEFG", start=1):
            cell = ws.cell(row=r, column=col, value=values[key])
            cell.font = _tfont()
            if key in ("D", "F") and values[key]:
                cell.number_format = DATE_FMT
                cell.fill = GREEN_FILL  # как в образце: дата блокировки подсвечена зелёным
    return ws


def google_rows(cases, start, end):
    """Строки листа «Поисковая выдача Google»: каждая жалоба в Google из окна
    «Жалобы» (и старое поле даты Google DMCA), поданная или закрытая в периоде."""
    s, e = _as_date(start), _as_date(end)
    rows = []
    for c in cases:
        entries = [x for x in (c.get("other_complaints") or []) if "google" in (x.get("method") or "").lower()]
        if c.get("google_dmca_filed_at") and not any(x.get("filed_at") == c["google_dmca_filed_at"] for x in entries):
            entries.append({"filed_at": c["google_dmca_filed_at"], "resolved_at": ""})
        for x in entries:
            filed, resolved = _as_date(x.get("filed_at")), _as_date(x.get("resolved_at"))
            if not ((filed and s <= filed <= e) or (resolved and s <= resolved <= e)):
                continue
            rows.append((filed or _dt.date.max, c.get("url", ""), f"Обращение от {_dm(x.get('filed_at'))}", resolved))
    rows.sort(key=lambda t: (t[0], t[3] or _dt.date.max, t[1]))
    return [(url, text, resolved) for _f, url, text, resolved in rows]


def _write_template_google_sheet(wb, sheet_title, cases, start, end):
    ws = wb.create_sheet(_unique_sheet_title(wb, sheet_title))
    ws.page_setup.orientation = "landscape"
    for col, width in zip("ABC", (48.6, 32.4, 28.6)):
        ws.column_dimensions[col].width = width
    for r, (url, text, resolved) in enumerate(google_rows(cases, start, end), start=1):
        ws.cell(row=r, column=1, value=url).font = _tfont()
        ws.cell(row=r, column=2, value=text).font = _tfont()
        cell = ws.cell(row=r, column=3, value=resolved)
        cell.font = _tfont()
        if resolved:
            cell.number_format = DATE_FMT
            cell.fill = GREEN_FILL
    return ws


def _contract_text(author):
    num, date = author.get("contract_number"), _as_date(author.get("contract_date"))
    if not num:
        return ""
    text = f"№ {num}"
    if date:
        text += f" от «{date.day:02d}» {_MONTHS_GENITIVE[date.month]} {date.year} года "
    return text


def _fee_text(fee):
    if fee in (None, ""):
        return "Общая стоимость оказанных услуг составляет ___ рублей."
    digits = re.sub(r"[^\d]", "", str(fee))
    pretty = f"{int(digits):,}".replace(",", "\u00a0") if digits else str(fee)
    return f"Общая стоимость оказанных услуг составляет {pretty} рублей."


def _write_template_act_sheet(wb, sheet_title, author, works, start, end, letterhead):
    ws = wb.create_sheet(_unique_sheet_title(wb, sheet_title))
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True  # при печати — на одну страницу по ширине
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    for col, width in zip("ABCD", (2.9, 24.1, 138.9, 13.9)):
        ws.column_dimensions[col].width = width
    center = Alignment(horizontal="center", vertical="center")
    left_c = Alignment(horizontal="left", vertical="center")

    head = "\n".join(p for p in (letterhead.get("name"), letterhead.get("email"), letterhead.get("phone"),
                                 letterhead.get("address")) if p) or DEFAULT_LETTERHEAD
    ws.merge_cells("C1:E1")
    c = ws.cell(row=1, column=3, value=head)
    c.font, c.alignment = _tfont(), Alignment(horizontal="left", wrap_text=True)
    ws.row_dimensions[1].height = 88.5
    c = ws.cell(row=2, column=3, value="АКТ ВЫПОЛНЕННЫХ РАБОТ")
    c.font, c.alignment = _tfont(), center
    if os.path.exists(ACT_LOGO):
        try:
            from openpyxl.drawing.image import Image as XLImage
            logo = XLImage(ACT_LOGO)
            logo.width = logo.height = 118  # как в образце: 1123950 EMU ≈ 118 пикс.
            ws.add_image(logo, "B1")
        except Exception:  # noqa — без логотипа акт всё равно нужен
            pass

    s, e = _as_date(start), _as_date(end)
    period = f"{s.strftime('%d.%m.%y')} 00:00 - {e.strftime('%d.%m.%y')} 23:59"
    def _quoted(t):
        t = (t or "").strip()
        return t if t.startswith("«") else f"«{t}»"
    titles = ", ".join(_quoted(w.get("title", "")) for w in works) or "—"
    fields = [(4, "Заказчик: ", author.get("customer_name") or author.get("name", "")),
              (5, "Договор: ", _contract_text(author)),
              (6, "Период: ", period),
              (7, "Предмет договора: ", "прекращение деятельности нелегального контента"),
              (8, "Наименования произведений : ", titles)]
    v_center = Alignment(vertical="center")
    for row, label, value in fields:
        lc = ws.cell(row=row, column=2, value=label)
        lc.font, lc.alignment = _tfont(color=LABEL_GRAY), left_c if row in (4, 5) else v_center
        vc = ws.cell(row=row, column=3, value=value)
        vc.font = _tfont()
        if row == 6:
            vc.alignment = v_center

    sites = [w.get("customer_site_url") for w in works if w.get("customer_site_url")]
    if sites:
        where = f", размещенное на сайте заказчика {', '.join(sites)}. Данный сайт рекламируются по сети в органической выдаче Яндекс, Google, социальных сетях VК и других площадках, принадлежащих Mail.ru"
    else:
        where = "."
    ws.merge_cells("B13:C13")
    c = ws.cell(row=13, column=2, value=(
        "Заказчик обратился к Исполнителю с заданием прекратить противоправные действия неустановленных лиц, "
        f"нарушающих авторские права Заказчика на произведение{where}"))
    c.font, c.alignment = _tfont(), Alignment(horizontal="left", vertical="top", wrap_text=True)
    ws.row_dimensions[13].height = 49.5

    lc = ws.cell(row=16, column=2, value="Перечень работ: : ")
    lc.font, lc.alignment = _tfont(color=LABEL_GRAY), Alignment(vertical="center")
    for i, text in enumerate(TEMPLATE_ACT_SERVICES):
        c = ws.cell(row=16 + i, column=3, value=text)
        c.font, c.alignment = _tfont(), left_c

    lc = ws.cell(row=27, column=2, value="Стоимость: ")
    lc.font, lc.alignment = _tfont(color=LABEL_GRAY), Alignment(vertical="center")
    for row, text in ((27, _fee_text(author.get("monthly_fee"))),
                      (28, "Оказанные услуги удовлетворяют требованиям Заказчика. Заказчик претензий не имеет."),
                      (29, "Настоящий акт составлен в двух экземплярах, один из которых находится у Исполнителя, второй – у Заказчика.")):
        c = ws.cell(row=row, column=3, value=text)
        c.font = _tfont()
        if row < 29:
            c.alignment = left_c
    for ref in ACT_BOTTOM_LINES:
        ws[ref].border = Border(bottom=ACT_LINE)
    for ref in ACT_TOP_LINES:
        ws[ref].border = Border(top=ACT_LINE)
    return ws


def build_protection_report(groups, period_start, period_end, letterhead):
    """groups — список по авторам:
        {"author": {...поля автора + реквизиты для акта...},
         "works": [(work, [cases]), ...],
         "other_cases": [cases без распознанного произведения],
         "act_works": [works для акта]}
    Один автор — листы названы в точности как в образце; несколько
    авторов — к названиям листов Google и акта добавляется фамилия."""
    wb = Workbook()
    wb.remove(wb.active)
    multi = len(groups) > 1
    for g in groups:
        author = g["author"]
        surname = (author.get("name") or "").split(" ")[0][:14]
        for work, cases in g["works"]:
            title = (work.get("title", "") or "Без названия").strip().lstrip("«").rstrip("»").strip() or "Без названия"
            if len(title) > 22:  # лимит Excel — 31 символ на имя листа; «Яндекс» в конце сохраняем
                title = title[:21].rstrip() + "…"
            _write_template_work_sheet(wb, f"\"{title}\" Яндекс", cases)
        if g.get("other_cases"):
            _write_template_work_sheet(wb, f"Прочие ссылки {surname}".strip(), g["other_cases"])
        all_cases = [c for _w, cs in g["works"] for c in cs] + list(g.get("other_cases") or [])
        _write_template_google_sheet(wb, f"Google — {surname}" if multi else "Поисковая выдача Google",
                                     all_cases, period_start, period_end)
        _write_template_act_sheet(wb, f"Акт — {surname}" if multi else "Акт выполненных работ",
                                  author, g.get("act_works") or [w for w, _ in g["works"]],
                                  period_start, period_end, letterhead)
    if not wb.sheetnames:
        wb.create_sheet("Нет данных").cell(row=1, column=1, value="За выбранный период данных нет.")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
