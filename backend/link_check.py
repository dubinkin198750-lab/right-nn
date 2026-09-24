"""Проверка, отвечает ли сайт по ссылке — обычный HTTP-запрос с коротким
таймаутом. Два независимых повода начать проверять конкретное дело:

1. Заявление подано (в суд и/или в РКН) — через 14 дней после **самой
   поздней** из этих двух дат подачи проверяем, не осталась ли ссылка
   всё ещё доступной несмотря на обращения. Если да — обращения явно не
   подействовали, дело помечается «требует повторной подачи»
   (needs_resend), чтобы его снова можно было выбрать и для заявления в
   суд, и для повторного обращения в РКН — по описанному пользователем
   процессу оба обращения переподаются вместе, не порознь.
2. Дело реально заблокировано (is_blocked() — см. ниже, любой из трёх
   этапов получил решение «заблокировано») — через 14 дней после самой
   блокировки проверяем, не заработала ли ссылка снова (случай нередкий —
   источник переезжает на тот же адрес через другой хостинг/CDN). Если
   заработала — ставится needs_resend, дело снова требует внимания
   (какое именно решение поправить — «первое» или «повторное» обращение —
   решает уже сам сотрудник вручную, автоматика не подменяет собой это
   решение).

Намеренно простая эвристика: «доступна» — сайт ответил кодом 200-399,
«недоступна» — любая другая ситуация (таймаут, обрыв соединения, DNS не
резолвится, код ошибки 4xx/5xx). Это не отличает «сайт заблокирован
Роскомнадзором» от «сайт просто временно не работает по другой причине» —
уточнить это можно только вручную, глядя на конкретный случай. Задача
этой проверки — не юридическое доказательство, а просто сигнал «стоит
посмотреть», чтобы не проверять все дела руками одно за другим.
"""
import os
import re
import time
from urllib.parse import urlparse

import requests

from . import appeals as appeals_mod

TIMEOUT = 10
CHECK_AFTER_DAYS = 14  # сколько ждать после «якорной» даты (см. _anchor) до самой первой проверки
RETRY_DELAY_SEC = 5  # пауза перед повторной попыткой, если первая не удалась
MAX_BODY_CHARS = 300_000  # сколько текста страницы смотреть в поисках заглушки

INTERVAL_SECONDS = {
    "hour": 3600,
    "day": 86400,
    "week": 7 * 86400,
    "month": 30 * 86400,
}
DEFAULT_INTERVAL = "day"

# Оставлено для совместимости со скриптами, которые импортируют константу.
APPEAL_STAGE_FIELDS = ("claim_decision", "first_appeal_decision", "repeat_appeal_decision")

# Проверка через прокси. Если сервер приложения стоит НЕ в России, блокировки
# РКН на него не действуют и заблокированный сайт с него открывается как
# обычно — такая проверка всегда будет показывать «доступна». Укажите в .env
# адрес российского прокси, например:
#   LINK_CHECK_PROXY=http://user:pass@1.2.3.4:3128
LINK_CHECK_PROXY_ENV = "LINK_CHECK_PROXY"

# Признаки страницы-заглушки провайдера / РКН. Если конечный адрес после
# редиректов ведёт на такой хост или текст страницы содержит такую фразу —
# ссылка считается заблокированной, даже если сервер ответил 200.
STUB_HOST_MARKERS = (
    "warning.rt.ru", "blocked.mts.ru", "zapret.beeline.ru", "blocklist.rkn.gov.ru",
    "eais.rkn.gov.ru", "block.megafon.ru", "fz139.ttk.ru", "blocked.tele2.ru",
    "zapret.domru.ru",
)
STUB_TEXT_MARKERS = (
    "доступ к информационному ресурсу ограничен",
    "доступ к ресурсу ограничен",
    "доступ ограничен на основании",
    "ресурс заблокирован",
    "единый реестр доменных имен",
    "единого реестра доменных имен",
    "реестр запрещенных сайтов",
    "реестр запрещённых сайтов",
    "по решению органов государственной власти",
    "eais.rkn.gov.ru",
    "149-фз",
)


def _proxies():
    proxy = (os.environ.get(LINK_CHECK_PROXY_ENV) or "").strip()
    return {"http": proxy, "https": proxy} if proxy else None


def _str_or_empty(value):
    return value if isinstance(value, str) else ""


def _page_title(text):
    m = re.search(r"<title[^>]*>(.*?)</title>", text or "", re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:150] if m else ""


def _looks_like_stub(final_url, text):
    host = (urlparse(final_url).hostname or "").lower() if final_url else ""
    if host and (host.startswith("blocked.") or any(host == m or host.endswith("." + m) for m in STUB_HOST_MARKERS)):
        return True
    lowered = (text or "").lower()
    return any(marker in lowered for marker in STUB_TEXT_MARKERS)


def _single_attempt(url, details=None):
    """Один HTTP-запрос — True, если сайт ответил кодом 200-399 и это не
    страница-заглушка о блокировке. Подробности (код, конечный адрес,
    заголовок страницы) пишутся в details, если он передан."""
    try:
        resp = requests.get(
            url, timeout=TIMEOUT, allow_redirects=True, proxies=_proxies(),
            headers={"User-Agent": "Mozilla/5.0 (compatible; PiracyMonitorBot/1.0)"},
        )
    except requests.RequestException as e:
        if details is not None:
            details.update({"http_code": None, "final_url": "", "title": "", "stub": False,
                            "error": type(e).__name__})
        return False
    code = resp.status_code
    final_url = _str_or_empty(getattr(resp, "url", "")) or url
    text = _str_or_empty(getattr(resp, "text", ""))[:MAX_BODY_CHARS]
    stub = _looks_like_stub(final_url, text)
    if details is not None:
        details.update({"http_code": code if isinstance(code, int) else None, "final_url": final_url,
                        "title": _page_title(text), "stub": stub, "error": ""})
    return isinstance(code, int) and 200 <= code < 400 and not stub


def check(url, details=None):
    """Возвращает ("доступна"|"недоступна", unix-время проверки).

    Делает вторую попытку перед тем, как заключить «недоступна» — один
    случайный сетевой сбой на нашей стороне не должен запускать
    последствия. Страница-заглушка провайдера/РКН считается «недоступна».
    Если передан словарь details — в него записываются подробности
    последней попытки (код ответа, конечный адрес, заголовок страницы),
    чтобы сотрудник видел, почему программа так решила."""
    if _single_attempt(url, details):
        return "доступна", time.time()
    if details is not None and details.get("stub"):
        return "недоступна", time.time()  # заглушка — повторять незачем
    time.sleep(RETRY_DELAY_SEC)
    if _single_attempt(url, details):
        return "доступна", time.time()
    return "недоступна", time.time()


def signature(details):
    """Отпечаток ответа сайта — чтобы после «Ложная тревога» не возвращать
    дело снова и снова, пока сайт отвечает ровно тем же самым."""
    if not details:
        return ""
    host_path = ""
    if details.get("final_url"):
        parsed = urlparse(details["final_url"])
        host_path = f"{(parsed.hostname or '').lower()}{parsed.path or ''}"
    return f"{details.get('http_code')}|{host_path}|{(details.get('title') or '').lower()}"


def is_blocked(case):
    """Дело заблокировано, если «заблокировано» стоит на ПОСЛЕДНЕМ начатом
    этапе (претензия → обращение №1 → №2 ...). См. appeals.current_decision."""
    return appeals_mod.is_blocked(case)


def appeal_failed(case):
    """Последнее обращение в МГС/РКН отклонено или без реакции (досудебная
    претензия сюда не входит — её провал означает просто переход к
    обращению)."""
    return appeals_mod.last_attempt_failed(case)


def _anchor_date(case):
    """От какой даты отсчитываем 14 дней до первой проверки для этого
    дела. У заблокированных (is_blocked()) — от даты блокировки
    (проверяем, не ожила ли ссылка снова). У всех остальных — от **самой
    поздней** из всех дат подачи, которые есть (первое заявление в суд,
    первое обращение в РКН, повторное заявление, повторное обращение) —
    именно с последнего реального действия имеет смысл давать новый срок
    на реакцию, а не с более старой, уже устаревшей даты."""
    if is_blocked(case):
        # Если хоть один из трёх этапов дал «заблокировано» — единственная
        # осмысленная дата отсчёта дальше это block_date (проверяем, не
        # ожила ли ссылка). Если она ещё не заполнена — мониторить пока
        # нечем и не нужно: раньше здесь код проваливался обратно к датам
        # подачи заявления, и если они были проставлены (например, ещё до
        # того, как претензия подействовала), через 14 дней автоматика
        # ошибочно включала needs_resend и снова открывала чекбокс
        # заявления по уже закрытому делу.
        return case.get("block_date") or None
    dates = appeals_mod.filing_dates(case)
    if not dates:
        return None
    return max(dates)  # строки формата YYYY-MM-DD сравниваются лексикографически корректно


def is_due(case, now=None):
    """Дело «созрело» для (повторной) проверки — см. _anchor_date для
    того, откуда берётся дата отсчёта. С неё должно пройти не меньше
    CHECK_AFTER_DAYS до первой проверки; дальше повторяется с выбранным
    для этого дела интервалом (по умолчанию — раз в день).

    Повторяется бессрочно, пока дело не уйдёт из активной таблицы
    (архивация после отчёта или удаление) — отдельного флага «остановить»
    не требуется, наблюдатель просто больше не увидит это дело в
    storage.load_blocking_cases()."""
    anchor = _anchor_date(case)
    if not anchor:
        return False
    try:
        anchor_ts = time.mktime(time.strptime(anchor, "%Y-%m-%d"))
    except ValueError:
        return False
    now = now if now is not None else time.time()
    if now - anchor_ts < CHECK_AFTER_DAYS * 86400:
        return False  # ещё рано для самой первой проверки

    checked_at = case.get("link_checked_at")
    if not checked_at:
        return True  # первая проверка уже созрела, интервал ещё не применялся

    interval = INTERVAL_SECONDS.get(case.get("link_check_interval") or DEFAULT_INTERVAL, INTERVAL_SECONDS[DEFAULT_INTERVAL])
    return now - checked_at >= interval


def build_update_patch(case, status, checked_at, details=None):
    """Что менять в деле по результату проверки. Общая для фонового
    наблюдателя и для ручной кнопки «Проверить сейчас».

    Если сотрудник раньше нажал «Ложная тревога — ссылка заблокирована»
    по ровно такому же ответу сайта (тот же код, адрес, заголовок) —
    результат «доступна» не поднимает тревогу повторно."""
    sig = signature(details)
    if status == "доступна" and sig and sig == case.get("false_alarm_signature"):
        status = "недоступна"
    patch = {"link_status": status, "link_checked_at": checked_at}
    patch["needs_resend"] = status == "доступна"
    if details is not None:
        patch["link_check_details"] = {
            "http_code": details.get("http_code"),
            "final_url": details.get("final_url", ""),
            "title": details.get("title", ""),
            "stub": bool(details.get("stub")),
            "error": details.get("error", ""),
            "signature": sig,
            "via_proxy": bool(_proxies()),
        }
    return patch
