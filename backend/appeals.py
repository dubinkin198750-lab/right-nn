"""Обращения в МГС и РКН — единый повторяющийся блок вместо россыпи
отдельных полей.

Раньше у дела были фиксированные поля: «№ определения Мосгорсуда» (одно
текстовое поле, куда вписывали и дату, и номер), «Обращение в РКН»
(номер + дата), «Повторное обращение» (две даты без подписи, без номеров),
«Решение (1-е)», «Решение (повторное)» и «Повторное решение» (свободный
текст). Сотрудники заполняли их наугад: номер повторного определения МГС
оказывался в «Повторном решении», номер повторного обращения в РКН — в
«Примечаниях».

Теперь у дела есть список `appeals`, каждый элемент — одно обращение:

    {"mgs_date": "2026-08-04",   # дата ОПРЕДЕЛЕНИЯ Мосгорсуда (не подачи)
     "mgs_number": "2И-6684",
     "rkn_date": "2026-08-07",
     "rkn_number": "2026-08-07-5...",
     "decision": "заблокировано" | "отклонено" | "нет реакции" | ""}

Обращений может быть сколько угодно (№1, №2, №3...). Следующее
добавляется, когда предыдущее отклонено / без реакции, либо когда
проверка показала, что заблокированная ссылка снова открылась.

Совместимость: старые поля (court_ruling_number, rkn_number,
first_appeal_decision, repeat_* ...) НЕ удаляются, а поддерживаются как
«зеркало» списка appeals (см. legacy_mirror). Отчёты, CSV, аналитика,
генерация заявлений и старые данные продолжают работать без переделки.
Для дел, у которых списка appeals ещё нет (всё, что заведено до этого
обновления), он строится на лету из старых полей (derive_from_legacy) —
отдельная миграция данных не обязательна, но есть скрипт
backend/migrate_appeals.py, который записывает результат на диск и
показывает дела, требующие ручной проверки.
"""
import re
import time

DECISIONS = ("", "заблокировано", "отклонено", "нет реакции")
FAILED_DECISIONS = ("отклонено", "нет реакции")
APPEAL_KEYS = ("mgs_date", "mgs_number", "rkn_date", "rkn_number", "decision")

# Поля старой модели, которые теперь считаются производными от appeals.
LEGACY_APPEAL_FIELDS = (
    "court_ruling_number", "court_ruling_date", "rkn_number", "rkn_filed_at",
    "first_appeal_decision", "repeat_ruling", "repeat_rkn_filed_at", "repeat_appeal_decision",
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# «04.08 2И-6684», «25.08.2026 2И-7238», «4/8 2И-1», «04.08.26 № 2И-1»
_RULING_TEXT_RE = re.compile(
    r"^\s*(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?\s*[,;]?\s*(?:№\s*)?(.*)$"
)


def empty_appeal():
    return {k: "" for k in APPEAL_KEYS}


def _clean(appeal):
    """Приводит одно обращение к строгому виду: только известные ключи,
    строки без пробелов по краям, решение — из допустимого списка, даты —
    только в формате YYYY-MM-DD (иначе пусто)."""
    out = empty_appeal()
    if not isinstance(appeal, dict):
        return out
    for k in APPEAL_KEYS:
        v = appeal.get(k)
        out[k] = v.strip() if isinstance(v, str) else ""
    for k in ("mgs_date", "rkn_date"):
        if out[k] and not _DATE_RE.match(out[k]):
            out[k] = ""
    if out["decision"] not in DECISIONS:
        out["decision"] = ""
    return out


def validate_appeals(value):
    """Проверка того, что пришло от клиента. Возвращает (список, ошибка)."""
    if not isinstance(value, list):
        return None, "appeals должен быть списком"
    if len(value) > 50:
        return None, "Слишком много обращений в одном деле"
    for i, a in enumerate(value, 1):
        if not isinstance(a, dict):
            return None, f"Обращение №{i}: неверный формат"
        if (a.get("decision") or "") not in DECISIONS:
            return None, f"Обращение №{i}: недопустимый статус «{a.get('decision')}». Разрешены: {list(DECISIONS)}"
        for k in ("mgs_date", "rkn_date"):
            v = a.get(k) or ""
            if v and not _DATE_RE.match(v):
                return None, f"Обращение №{i}: дата должна быть в формате ГГГГ-ММ-ДД"
    return [_clean(a) for a in value], None


def _has_content(appeal):
    return any(appeal.get(k) for k in APPEAL_KEYS)


def parse_ruling_text(text, fallback_year=None, reference_date=None):
    """«04.08 2И-6684» -> ("2026-08-04", "2И-6684").

    Если год в тексте не указан, он подбирается по reference_date (соседней
    дате этого же дела, например дате обращения в РКН): берётся год
    reference_date, но если получившаяся дата оказывается позже неё больше
    чем на месяц, берётся предыдущий год. Так «04.12» при обращении в РКН
    10.01.2027 превращается в 04.12.2026, а не в 04.12.2027.
    Без reference_date — fallback_year, а без него — текущий год с той же
    поправкой относительно сегодняшнего дня.
    Если текст не похож на «дата номер» — возвращает ("", text) без
    изменений, чтобы ничего не потерять."""
    text = (text or "").strip()
    if not text:
        return "", ""
    m = _RULING_TEXT_RE.match(text)
    if not m:
        return "", text
    d, mo, y, rest = m.groups()
    try:
        day, month = int(d), int(mo)
        if not (1 <= day <= 31 and 1 <= month <= 12):
            return "", text
        if y:
            year = int(y)
            if year < 100:
                year += 2000
        else:
            if reference_date and _DATE_RE.match(str(reference_date)):
                ref = str(reference_date)
            elif fallback_year:
                ref = f"{int(fallback_year):04d}-12-31"
            else:
                ref = time.strftime("%Y-%m-%d")
            year = int(ref[:4])
            candidate = time.mktime(time.strptime(f"{year:04d}-{month:02d}-{min(day, 28):02d}", "%Y-%m-%d"))
            if candidate - time.mktime(time.strptime(ref, "%Y-%m-%d")) > 31 * 86400:
                year -= 1
        iso = f"{year:04d}-{month:02d}-{day:02d}"
        time.strptime(iso, "%Y-%m-%d")  # отсекаем 31.02 и т.п.
    except ValueError:
        return "", text
    return iso, rest.strip()


def _year_of(*dates):
    for d in dates:
        if d and _DATE_RE.match(str(d)):
            return int(str(d)[:4])
    return None


def _first_date(*dates):
    for d in dates:
        if d and _DATE_RE.match(str(d)):
            return str(d)
    return None


def derive_from_legacy(case):
    """Строит список обращений из полей старой модели. Ничего не
    выбрасывает: если текст номера не удаётся надёжно разобрать или дата в
    тексте расходится с уже заполненной датой определения, текст остаётся
    в поле номера целиком."""
    fallback_year = _year_of(
        case.get("court_ruling_date"), case.get("rkn_filed_at"), case.get("petition_filed_at"),
        case.get("claim_date"), case.get("discovered_at"),
    )
    if fallback_year is None and case.get("added_at"):
        try:
            fallback_year = time.localtime(float(case["added_at"])).tm_year
        except (TypeError, ValueError):
            fallback_year = None

    first = empty_appeal()
    number_text = (case.get("court_ruling_number") or "").strip()
    ref1 = _first_date(case.get("rkn_filed_at"), case.get("petition_filed_at"), case.get("block_date"))
    parsed_date, parsed_number = parse_ruling_text(number_text, fallback_year, ref1)
    stored_date = case.get("court_ruling_date") or ""
    if parsed_date and stored_date and parsed_date != stored_date:
        # в тексте одна дата, в поле «дата определения» другая — не
        # выбираем за человека, сохраняем текст как есть
        first["mgs_date"] = stored_date
        first["mgs_number"] = number_text
    else:
        first["mgs_date"] = stored_date or parsed_date
        first["mgs_number"] = parsed_number if parsed_date else number_text
    first["rkn_date"] = case.get("rkn_filed_at") or ""
    first["rkn_number"] = case.get("rkn_number") or ""
    first["decision"] = case.get("first_appeal_decision") or ""

    second = empty_appeal()
    ref2 = _first_date(case.get("repeat_rkn_filed_at"), case.get("repeat_petition_filed_at"), case.get("block_date"), ref1)
    r_date, r_number = parse_ruling_text(case.get("repeat_ruling") or "", fallback_year, ref2)
    second["mgs_date"] = r_date
    second["mgs_number"] = r_number
    second["rkn_date"] = case.get("repeat_rkn_filed_at") or ""
    second["decision"] = case.get("repeat_appeal_decision") or ""
    has_second = _has_content(second) or bool(case.get("repeat_petition_filed_at"))

    result = []
    if _has_content(first) or has_second:
        result.append(_clean(first))
    if has_second:
        result.append(_clean(second))
    return result


# Копия исходных значений старых полей — сохраняется в деле один раз, в
# момент, когда у него впервые появляется список appeals (скрипт переноса
# или первое сохранение обращений из интерфейса). Старые поля после этого
# становятся копией нового списка, а оригинал остаётся здесь навсегда —
# на случай неверного разбора даты или отката на прежнюю версию.
LEGACY_BACKUP_KEY = "legacy_appeal_fields_backup"
LEGACY_BACKUP_FIELDS = LEGACY_APPEAL_FIELDS + ("repeat_petition_filed_at", "block_date", "notes")


def legacy_backup(case):
    """Словарь исходных значений для сохранения, либо None, если копия у
    дела уже есть или список appeals уже был записан раньше."""
    if LEGACY_BACKUP_KEY in case or isinstance(case.get("appeals"), list):
        return None
    backup = {f: case.get(f, "") for f in LEGACY_BACKUP_FIELDS}
    backup["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return backup


def get_appeals(case):
    """Список обращений дела — сохранённый, либо построенный из старых полей."""
    stored = case.get("appeals")
    if isinstance(stored, list):
        return [_clean(a) for a in stored]
    return derive_from_legacy(case)


def _ruling_text(appeal):
    parts = []
    if appeal.get("mgs_date"):
        y, m, d = appeal["mgs_date"].split("-")
        parts.append(f"{d}.{m}.{y}")
    if appeal.get("mgs_number"):
        parts.append(appeal["mgs_number"])
    return " ".join(parts)


def legacy_mirror(appeals):
    """Значения старых полей, вычисленные из списка обращений — чтобы
    отчёты/CSV/аналитика, читающие старые поля, видели актуальные данные."""
    first = appeals[0] if appeals else empty_appeal()
    mirror = {
        "court_ruling_date": first["mgs_date"],
        "court_ruling_number": first["mgs_number"],
        "rkn_filed_at": first["rkn_date"],
        "rkn_number": first["rkn_number"],
        "first_appeal_decision": first["decision"],
        "repeat_ruling": "",
        "repeat_rkn_filed_at": "",
        "repeat_appeal_decision": "",
    }
    if len(appeals) >= 2:
        last = appeals[-1]
        mirror["repeat_ruling"] = "; ".join(filter(None, (_ruling_text(a) for a in appeals[1:])))
        mirror["repeat_rkn_filed_at"] = last["rkn_date"]
        mirror["repeat_appeal_decision"] = last["decision"]
    return mirror


def apply_legacy_patch(existing, patch):
    """Если клиент (старая версия интерфейса, скрипт, тест) прислал старые
    поля вместо appeals — переносим их в список обращений, не теряя
    обращения №3 и дальше, если они есть."""
    appeals = get_appeals(existing)
    touched = [f for f in LEGACY_APPEAL_FIELDS if f in patch]
    if not touched:
        return None
    first_fields = ("court_ruling_number", "court_ruling_date", "rkn_number", "rkn_filed_at", "first_appeal_decision")
    repeat_fields = ("repeat_ruling", "repeat_rkn_filed_at", "repeat_appeal_decision")
    if any(f in patch for f in first_fields) and not appeals:
        appeals.append(empty_appeal())
    if any(f in patch for f in repeat_fields):
        while len(appeals) < 2:
            appeals.append(empty_appeal())
    if appeals:
        a = appeals[0]
        if "court_ruling_number" in patch:
            ref = _first_date(a["rkn_date"], existing.get("petition_filed_at"))
            d, n = parse_ruling_text(patch["court_ruling_number"] or "", _year_of(a["mgs_date"]), ref)
            a["mgs_number"] = n if d else (patch["court_ruling_number"] or "").strip()
            if d and not patch.get("court_ruling_date") and not a["mgs_date"]:
                a["mgs_date"] = d
        if "court_ruling_date" in patch:
            a["mgs_date"] = patch["court_ruling_date"] or ""
        if "rkn_number" in patch:
            a["rkn_number"] = patch["rkn_number"] or ""
        if "rkn_filed_at" in patch:
            a["rkn_date"] = patch["rkn_filed_at"] or ""
        if "first_appeal_decision" in patch:
            a["decision"] = patch["first_appeal_decision"] or ""
    if len(appeals) >= 2:
        last = appeals[-1]
        if "repeat_ruling" in patch:
            ref = _first_date(last["rkn_date"], appeals[0]["rkn_date"])
            d, n = parse_ruling_text(patch["repeat_ruling"] or "", _year_of(appeals[0]["mgs_date"]), ref)
            last["mgs_number"] = n if d else (patch["repeat_ruling"] or "").strip()
            if d:
                last["mgs_date"] = d
        if "repeat_rkn_filed_at" in patch:
            last["rkn_date"] = patch["repeat_rkn_filed_at"] or ""
        if "repeat_appeal_decision" in patch:
            last["decision"] = patch["repeat_appeal_decision"] or ""
    return [_clean(a) for a in appeals]


def stages(case):
    """Этапы дела по порядку: претензия, затем обращения. Возвращает
    список словарей {"kind", "decision", "has_content"}."""
    result = [{
        "kind": "claim",
        "decision": case.get("claim_decision") or "",
        "has_content": bool(case.get("claim_date") or case.get("claim_decision")),
    }]
    for a in get_appeals(case):
        result.append({"kind": "appeal", "decision": a["decision"], "has_content": _has_content(a)})
    return result


def current_decision(case):
    """Решение по ПОСЛЕДНЕМУ начатому этапу — именно оно определяет
    текущее состояние дела. Раньше дело считалось заблокированным, если
    «заблокировано» стояло на ЛЮБОМ этапе: после того как ссылка ожила и
    было подано повторное обращение, старое «заблокировано» на первом
    обращении продолжало считаться текущим."""
    present = [s for s in stages(case) if s["has_content"]]
    if not present:
        return ""
    return present[-1]["decision"]


def is_blocked(case):
    return current_decision(case) == "заблокировано"


def last_attempt_failed(case):
    """Последнее обращение (не претензия) отклонено или осталось без
    реакции — пора готовить следующее."""
    appeals = [a for a in get_appeals(case) if _has_content(a)]
    return bool(appeals) and appeals[-1]["decision"] in FAILED_DECISIONS


def filing_dates(case):
    """Все даты подачи/определений по делу — для отсчёта 14 дней до
    первой проверки ссылки."""
    dates = [case.get("petition_filed_at"), case.get("repeat_petition_filed_at")]
    for a in get_appeals(case):
        dates.extend([a["mgs_date"], a["rkn_date"]])
    return [d for d in dates if d]


def new_dates_added(old_appeals, new_appeals):
    """Появилась ли в новом списке дата, которой не было в старом —
    признак реальной новой подачи (а не правки опечатки)."""
    old = {(i, k, a[k]) for i, a in enumerate(old_appeals) for k in ("mgs_date", "rkn_date") if a[k]}
    for i, a in enumerate(new_appeals):
        for k in ("mgs_date", "rkn_date"):
            if a[k] and (i, k, a[k]) not in old:
                is_new_slot = i >= len(old_appeals) or not old_appeals[i][k]
                if is_new_slot:
                    return True
    return False


def summary_lines(case):
    """Человекочитаемое описание всех обращений — для Excel/CSV/архива."""
    lines = []
    for i, a in enumerate(get_appeals(case), 1):
        parts = []
        mgs = _ruling_text(a)
        if mgs:
            parts.append(f"МГС: {mgs}")
        rkn = []
        if a["rkn_date"]:
            y, m, d = a["rkn_date"].split("-")
            rkn.append(f"{d}.{m}.{y}")
        if a["rkn_number"]:
            rkn.append(f"№ {a['rkn_number']}")
        if rkn:
            parts.append("РКН: " + " ".join(rkn))
        parts.append(f"статус: {a['decision'] or 'не определено'}")
        lines.append(f"№{i} — " + "; ".join(parts))
    return lines
