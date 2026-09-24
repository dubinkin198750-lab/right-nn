"""Аналитика для раздела «Аналитика» (только admin) — три помесячных
среза: сколько обнаружено новых ссылок, сколько реально заблокировано,
и сравнение динамики обнаружения/блокировки между собой.

Источники данных:
- «обнаружено» — берётся из журнала действий (audit_log.json), запись
  «добавил в блокировку» пишется туда с самого начала работы приложения,
  так что помесячная аналитика строится даже по старым данным, не только
  с момента появления этого раздела.
- «заблокировано» — берётся из block_date дел блокировки, причём **и**
  активных (blocking_cases.json), **и** уже заархивированных после
  завершения месячного отчёта (report_archive.json) — иначе после каждой
  архивации исторические цифры «терялись» бы из статистики.

Никакой денежной оценки («упущенная прибыль» и т.п.) сознательно не
делает — для этого понадобились бы реальные данные о цене, которых в
проекте пока нет (обсуждали отдельно и решили пока не добавлять)."""
import re
from collections import Counter, defaultdict
from urllib.parse import urlparse


def _month_key(date_str_or_ts):
    """Приводит и unix-время (float/int), и строку вида YYYY-MM-DD к ключу
    месяца "YYYY-MM". Возвращает None, если распознать не удалось —
    вызывающий код должен просто пропускать такие записи, не падать."""
    if not date_str_or_ts:
        return None
    if isinstance(date_str_or_ts, (int, float)):
        import time
        return time.strftime("%Y-%m", time.localtime(date_str_or_ts))
    s = str(date_str_or_ts)
    m = re.match(r"^(\d{4}-\d{2})", s)
    return m.group(1) if m else None


def _domain(url):
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:  # noqa
        return ""


def _last_n_months(n, from_month=None):
    """Список последних n ключей месяца по порядку возрастания — так на
    графике всегда виден непрерывный ряд месяцев, даже если за какой-то
    месяц данных не было вообще (тогда там будет честный ноль, а не
    выпадающая точка)."""
    import time
    if from_month:
        year, month = map(int, from_month.split("-"))
    else:
        now = time.localtime()
        year, month = now.tm_year, now.tm_mon
    months = []
    for _ in range(n):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(months))


def detected_per_month(audit_log_entries, months=12):
    """Сколько новых ссылок добавлено в блокировку по месяцам — из
    журнала действий (action == "добавил в блокировку"), плюс топ доменов
    за всё время, что есть в журнале (не только за последние N месяцев —
    домены имеет смысл сравнивать по всей истории, не обрезая)."""
    month_counts = Counter()
    domain_counts = Counter()
    for entry in audit_log_entries:
        if entry.get("action") != "добавил в блокировку":
            continue
        key = _month_key(entry.get("ts"))
        if key:
            month_counts[key] += 1
        # details обычно вида "название (https://example.com/page)" —
        # достаём ссылку из скобок, чтобы посчитать домен
        details = entry.get("details", "")
        m = re.search(r"\((https?://[^)]+)\)", details)
        if m:
            domain = _domain(m.group(1))
            if domain:
                domain_counts[domain] += 1

    labels = _last_n_months(months)
    series = [month_counts.get(m, 0) for m in labels]
    top_domains = domain_counts.most_common(10)
    return {
        "months": labels,
        "counts": series,
        "top_domains": [{"domain": d, "count": c} for d, c in top_domains],
        "total_all_time": sum(month_counts.values()),
    }


def blocked_per_month(blocking_cases, archived_cases, months=12):
    """Сколько дел реально заблокировано по месяцам (block_date) — считает
    и активные, и уже заархивированные дела, чтобы завершение месячного
    отчёта (которое переносит дела в архив) не «съедало» историю."""
    from . import link_check

    month_counts = Counter()
    outcome_counts = Counter()

    for case in blocking_cases:
        # общего единого «статуса» дела больше нет (см. link_check.py) —
        # вместо разбивки по нему считаем по факту: заблокировано и
        # держится / нужна повторная подача / всё ещё в процессе (ни то,
        # ни другое пока не определилось)
        if link_check.is_blocked(case) and not case.get("needs_resend"):
            outcome_counts["заблокировано"] += 1
        elif case.get("needs_resend"):
            outcome_counts["нужна повторная подача"] += 1
        else:
            outcome_counts["в процессе"] += 1
        if link_check.is_blocked(case):
            key = _month_key(case.get("block_date"))
            if key:
                month_counts[key] += 1

    for entry in archived_cases:
        # архивные записи по определению уже были «заблокировано» на
        # момент архивации — считаем их все
        key = _month_key(entry.get("block_date"))
        if key:
            month_counts[key] += 1

    labels = _last_n_months(months)
    series = [month_counts.get(m, 0) for m in labels]
    return {
        "months": labels,
        "counts": series,
        "status_breakdown": dict(outcome_counts),
        "total_blocked_all_time": sum(month_counts.values()),
    }


def spread_dynamics(audit_log_entries, blocking_cases, archived_cases, months=12):
    """Сравнение динамики «обнаружено» и «заблокировано» месяц к месяцу —
    отдельно посчитанные ряды из двух функций выше, сведённые в один
    ответ для одного графика с двумя линиями. Плюс простая метрика
    «скорость реакции»: медианное число дней между добавлением ссылки в
    блокировку и датой её фактической блокировки, по тем делам, где обе
    даты известны — грубая, но честная оценка того, насколько быстро
    цепочка «нашли → заблокировали» отрабатывает на практике."""
    detected = detected_per_month(audit_log_entries, months=months)
    blocked = blocked_per_month(blocking_cases, archived_cases, months=months)

    added_at_by_url = {}
    for entry in audit_log_entries:
        if entry.get("action") != "добавил в блокировку":
            continue
        m = re.search(r"\((https?://[^)]+)\)", entry.get("details", ""))
        if m and entry.get("ts"):
            added_at_by_url.setdefault(m.group(1), entry["ts"])

    import time
    deltas_days = []
    all_cases = list(blocking_cases) + list(archived_cases)
    for case in all_cases:
        added_ts = added_at_by_url.get(case.get("url"))
        block_date = case.get("block_date")
        if not added_ts or not block_date:
            continue
        try:
            block_ts = time.mktime(time.strptime(block_date, "%Y-%m-%d"))
        except ValueError:
            continue
        delta = (block_ts - added_ts) / 86400
        if delta >= 0:  # отрицательное значит опечатку в дате — не учитываем
            deltas_days.append(delta)

    median_days = None
    if deltas_days:
        deltas_days.sort()
        mid = len(deltas_days) // 2
        median_days = deltas_days[mid] if len(deltas_days) % 2 else (deltas_days[mid - 1] + deltas_days[mid]) / 2

    return {
        "months": detected["months"],
        "detected_counts": detected["counts"],
        "blocked_counts": blocked["counts"],
        "median_days_to_block": round(median_days, 1) if median_days is not None else None,
        "cases_with_known_delay": len(deltas_days),
    }


def apply_overrides(months, counts, overrides):
    """Подставляет ручные поправки поверх автоматически посчитанных чисел
    там, где они заданы — overrides это словарь {"2026-08": 15, ...}.
    Возвращает (итоговые_значения, флаги_is_overridden той же длины) —
    флаги нужны фронтенду, чтобы визуально отметить, какие цифры
    поправлены вручную, а какие посчитаны автоматически."""
    final_counts = []
    is_overridden = []
    for month, auto_value in zip(months, counts):
        if month in overrides:
            final_counts.append(overrides[month])
            is_overridden.append(True)
        else:
            final_counts.append(auto_value)
            is_overridden.append(False)
    return final_counts, is_overridden
