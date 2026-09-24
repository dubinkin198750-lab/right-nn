"""Хранилище на JSON-файлах: авторы, их произведения (работы) и общий
блок-лист доменов. Структура авторы -> произведения соответствует реальной
таблице из исходного n8n-сценария (столбцы автор / произведение / вопрос).
"""
import json
import os
import threading
import time
import uuid

from . import document_vault

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
AUTHORS_FILE = os.path.join(DATA_DIR, "authors.json")
WORKS_FILE = os.path.join(DATA_DIR, "works.json")
BLOCKLIST_FILE = os.path.join(DATA_DIR, "blocklist.json")
SITES_FILE = os.path.join(DATA_DIR, "sites.json")
BLOCKING_CASES_FILE = os.path.join(DATA_DIR, "blocking_cases.json")
REPORT_ARCHIVE_FILE = os.path.join(DATA_DIR, "report_archive.json")
BULK_SEARCH_BATCH_FILE = os.path.join(DATA_DIR, "bulk_search_batch.json")
DOCUMENTS_META_FILE = os.path.join(DATA_DIR, "documents.json")
EMPLOYEE_DOCUMENTS_META_FILE = os.path.join(DATA_DIR, "employee_documents.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
ANALYTICS_OVERRIDES_FILE = os.path.join(DATA_DIR, "analytics_overrides.json")
COMPLAINT_SEND_LOG_FILE = os.path.join(DATA_DIR, "complaint_send_log.json")
SCREENSHOTS_META_FILE = os.path.join(DATA_DIR, "screenshots.json")
AUDIT_LOG_FILE = os.path.join(DATA_DIR, "audit_log.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
INVITES_FILE = os.path.join(DATA_DIR, "invites.json")
DOCUMENT_ACCESS_GRANTS_FILE = os.path.join(DATA_DIR, "document_access_grants.json")
SITE_ACCESS_GRANTS_FILE = os.path.join(DATA_DIR, "site_access_grants.json")
RESULTS_DIR = os.path.join(DATA_DIR, "results")
DOCUMENTS_DIR = os.path.join(DATA_DIR, "documents")
SCREENSHOTS_DIR = os.path.join(DATA_DIR, "screenshots")

_lock = threading.RLock()  # RLock — чтобы составные операции ниже (upsert/delete/add)
# могли держать один и тот же лок на всё время «прочитать -> изменить -> записать»,
# в том числе когда изнутри вызывают другие load_*/save_* того же потока.

DEFAULT_BLOCKLIST = [
    "academymarketing.ru",
    "academy-neiro.ru",
    "alexander-fedyaev.ru",
    "all-info-products.ru",
    "app.lava.top",
    "belousova.academy",
    "dum.ai",
    "dvd-education.ru",
    "felitsyna.ru",
    "gotocourse.ru",
    "ibrain.ru",
    "info-hit.ru",
    "ironskills.by",
    "istudy.by",
    "kursmamavrach.com",
    "kursmamavrach.tilda.ws",
    "natafeli.pro",
    "neiro-profi.ru",
    "oplata.slems.ru",
    "professionals.beauty",
    "pult-ai.ru",
    "school.felitsyna.ru",
    "sofiaraketa.ru",
    "v8.1c.ru",
]

DEFAULT_AUTHOR = {"id": "demo-author", "name": "Демо-автор"}

DEFAULT_WORK = {
    "id": "demo-work",
    "author_id": "demo-author",
    "title": "Демо-произведение",
    "query": "название курса автора",
    "keywords": ["ключевое слово 1", "ключевое слово 2"],
    "negative_keywords": [],
    "pages": 7,
    "extra_blocked_domains": [],
    "customer_site_url": "",  # сайт заказчика с этим произведением — для текста акта в отчёте
    "active": True,
    "sources": {"yandex": True, "google": False, "duckduckgo": False, "avito": False, "telegram": False,
                "vk": False, "vk_video": False, "torrents": False},
}


DEFAULT_SITES = [
    {
        "id": "example-site",
        "name": "Пример (замените на реальный сайт)",
        "url_template": "https://example.com/search?q={query}",
    }
]


def _ensure_files():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(AUTHORS_FILE):
        with open(AUTHORS_FILE, "w", encoding="utf-8") as f:
            json.dump([DEFAULT_AUTHOR], f, ensure_ascii=False, indent=2)
    if not os.path.exists(WORKS_FILE):
        with open(WORKS_FILE, "w", encoding="utf-8") as f:
            json.dump([DEFAULT_WORK], f, ensure_ascii=False, indent=2)
    if not os.path.exists(BLOCKLIST_FILE):
        with open(BLOCKLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_BLOCKLIST, f, ensure_ascii=False, indent=2)
    if not os.path.exists(SITES_FILE):
        with open(SITES_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SITES, f, ensure_ascii=False, indent=2)
    if not os.path.exists(BLOCKING_CASES_FILE):
        with open(BLOCKING_CASES_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    if not os.path.exists(REPORT_ARCHIVE_FILE):
        with open(REPORT_ARCHIVE_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    if not os.path.exists(DOCUMENTS_META_FILE):
        with open(DOCUMENTS_META_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    if not os.path.exists(EMPLOYEE_DOCUMENTS_META_FILE):
        with open(EMPLOYEE_DOCUMENTS_META_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)
    if not os.path.exists(SCREENSHOTS_META_FILE):
        with open(SCREENSHOTS_META_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    if not os.path.exists(AUDIT_LOG_FILE):
        with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    if not os.path.exists(COMPLAINT_SEND_LOG_FILE):
        with open(COMPLAINT_SEND_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    if not os.path.exists(INVITES_FILE):
        with open(INVITES_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    if not os.path.exists(DOCUMENT_ACCESS_GRANTS_FILE):
        with open(DOCUMENT_ACCESS_GRANTS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    if not os.path.exists(SITE_ACCESS_GRANTS_FILE):
        with open(SITE_ACCESS_GRANTS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)


# ---------- authors ----------
def load_authors():
    _ensure_files()
    with _lock:
        with open(AUTHORS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_authors(authors):
    _ensure_files()
    with _lock:
        with open(AUTHORS_FILE, "w", encoding="utf-8") as f:
            json.dump(authors, f, ensure_ascii=False, indent=2)


def get_author(author_id):
    for a in load_authors():
        if a["id"] == author_id:
            return a
    return None


def upsert_author(author):
    with _lock:
        authors = load_authors()
        if not author.get("id"):
            author["id"] = str(uuid.uuid4())[:8]
        for i, a in enumerate(authors):
            if a["id"] == author["id"]:
                authors[i] = author
                save_authors(authors)
                return author
        authors.append(author)
        save_authors(authors)
        return author


def delete_author(author_id):
    with _lock:
        authors = [a for a in load_authors() if a["id"] != author_id]
        save_authors(authors)
        # каскадно удаляем все произведения этого автора и их сохранённые результаты
        removed_ids = [w["id"] for w in load_works() if w["author_id"] == author_id]
        works = [w for w in load_works() if w["author_id"] != author_id]
        save_works(works)
        for wid in removed_ids:
            delete_work_results(wid)
        # и все загруженные документы этого автора
        for doc in get_author_documents(author_id):
            document_vault.delete_encrypted(doc["stored_filename"])
            delete_document(doc["id"])


# ---------- works (произведения) ----------
def load_works():
    _ensure_files()
    with _lock:
        with open(WORKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_works(works):
    _ensure_files()
    with _lock:
        with open(WORKS_FILE, "w", encoding="utf-8") as f:
            json.dump(works, f, ensure_ascii=False, indent=2)


def get_work(work_id):
    for w in load_works():
        if w["id"] == work_id:
            return w
    return None


def list_works_by_author(author_id):
    return [w for w in load_works() if w["author_id"] == author_id]


def upsert_work(work):
    with _lock:
        works = load_works()
        if not work.get("id"):
            work["id"] = str(uuid.uuid4())[:8]
        for i, w in enumerate(works):
            if w["id"] == work["id"]:
                works[i] = work
                save_works(works)
                return work
        works.append(work)
        save_works(works)
        return work


def delete_work(work_id):
    with _lock:
        works = [w for w in load_works() if w["id"] != work_id]
        save_works(works)
        delete_work_results(work_id)


# ---------- shared domain blocklist ----------
def load_blocklist():
    _ensure_files()
    with _lock:
        with open(BLOCKLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_blocklist(domains):
    _ensure_files()
    with _lock:
        with open(BLOCKLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(set(d.strip().lower() for d in domains if d.strip())), f, ensure_ascii=False, indent=2)


# ---------- сохранённые результаты по произведению ----------
# Хранятся отдельно от разовых поисковых задач (jobs, в памяти) — это
# «постоянный» список по произведению: копируется, редактируется, удаляются
# отдельные строки, добавляются вручную — и переживает перезапуск сервера.
#
# Формат файла: {"is_fallback": bool, "items": [...]}
# is_fallback=True означает, что фильтр по словам не нашёл ни одного совпадения,
# и здесь сохранён весь необработанный список найденного, а не отфильтрованный —
# чтобы интерфейс мог явно это показать, а не выглядеть как «отфильтровано».
# Старые файлы (просто список без обёртки) читаются как is_fallback=False.
def _results_path(work_id):
    return os.path.join(RESULTS_DIR, f"{work_id}.json")


def load_work_results(work_id):
    path = _results_path(work_id)
    with _lock:
        if not os.path.exists(path):
            return {"is_fallback": False, "items": []}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    if isinstance(data, list):  # старый формат — просто список строк
        return {"is_fallback": False, "items": data}
    return data


def save_work_results(work_id, items, is_fallback=False):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with _lock:
        with open(_results_path(work_id), "w", encoding="utf-8") as f:
            json.dump({"is_fallback": is_fallback, "items": items}, f, ensure_ascii=False, indent=2)


# ---------- последний результат «Поиск по сайтам» ----------
# В отличие от результатов поиска по произведениям (см. save_work_results
# выше, привязано к work_id и сохраняется на диск), результат раздела
# «Поиск по сайтам» раньше жил только в памяти процесса (backend/jobs.py,
# _site_jobs) и в памяти вкладки браузера — при перезапуске сервера
# (обновление кода, штатный деплой) или просто при закрытии приложения
# список найденных ссылок пропадал бесследно, даже если сотрудник ещё не
# успел разобрать находки. Храним только ПОСЛЕДНИЙ результат (не историю
# всех запусков) — этого достаточно для восстановления после перезапуска,
# а не архив на будущее.
SITE_SEARCH_LAST_RESULT_FILE = os.path.join(DATA_DIR, "site_search_last_result.json")


def save_last_site_search_result(result):
    os.makedirs(DATA_DIR, exist_ok=True)
    with _lock:
        with open(SITE_SEARCH_LAST_RESULT_FILE, "w", encoding="utf-8") as f:
            json.dump({"saved_at": time.time(), "result": result}, f, ensure_ascii=False, indent=2)


def load_last_site_search_result():
    if not os.path.exists(SITE_SEARCH_LAST_RESULT_FILE):
        return None
    with _lock:
        with open(SITE_SEARCH_LAST_RESULT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def _normalize_url_for_dedup(url):
    """Приводит ссылку к каноническому виду для сравнения на дубль — иначе
    https://example.com/page и https://example.com/page/ (или http://
    вместо https://) считались бы двумя разными ссылками, хотя по сути это
    одна и та же страница. Намеренно НЕ трогаем регистр самого пути и
    query-параметров — в отличие от домена, они технически МОГУТ быть
    регистрозависимыми на некоторых серверах, тут лучше перестраховаться
    в сторону «не потерять законный дубль», а не наоборот."""
    if not url:
        return ""
    from urllib.parse import urlparse
    parsed = urlparse(url.strip())
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    normalized = f"{netloc}{path}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized


def add_work_result_row(work_id, row):
    """Возвращает добавленную строку, либо None, если такая ссылка у этого
    произведения уже есть — раньше проверка на дубль была только на
    фронтенде (state.savedResults), а бэкенд принимал что угодно. Это
    становится важным, когда результаты добавляются не только со страницы
    самого произведения (где на фронтенде точно есть актуальный список),
    но и, например, со страницы «Поиск по сайтам» — там такой гарантии нет.

    Сравнение — по нормализованной ссылке (см. _normalize_url_for_dedup),
    не по буквальному совпадению строки: иначе один и тот же адрес с
    завершающим слэшем или с http:// вместо https:// проходил бы как
    «другая» ссылка."""
    with _lock:
        data = load_work_results(work_id)
        new_norm = _normalize_url_for_dedup(row.get("url"))
        if any(_normalize_url_for_dedup(existing.get("url")) == new_norm for existing in data["items"]):
            return None
        row = dict(row)
        if not row.get("id"):
            row["id"] = str(uuid.uuid4())[:8]
        data["items"].append(row)
        # добавление ссылки вручную — это уже осознанная правка, больше не «аварийный откат»
        save_work_results(work_id, data["items"], is_fallback=False)
        return row


def delete_work_result_row(work_id, row_id):
    with _lock:
        data = load_work_results(work_id)
        items = [r for r in data["items"] if r.get("id") != row_id]
        save_work_results(work_id, items, is_fallback=data["is_fallback"])


def delete_work_results(work_id):
    path = _results_path(work_id)
    with _lock:
        if os.path.exists(path):
            os.remove(path)


# ---------- справочник сайтов для прямого поиска ----------
def load_sites():
    _ensure_files()
    with _lock:
        with open(SITES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_sites(sites):
    _ensure_files()
    with _lock:
        with open(SITES_FILE, "w", encoding="utf-8") as f:
            json.dump(sites, f, ensure_ascii=False, indent=2)


def get_site(site_id):
    for s in load_sites():
        if s["id"] == site_id:
            return s
    return None


def upsert_site(site):
    with _lock:
        sites = load_sites()
        if not site.get("id"):
            site["id"] = str(uuid.uuid4())[:8]
        for i, s in enumerate(sites):
            if s["id"] == site["id"]:
                sites[i] = site
                save_sites(sites)
                return site
        sites.append(site)
        save_sites(sites)
        return site


def delete_site(site_id):
    with _lock:
        sites = [s for s in load_sites() if s["id"] != site_id]
        save_sites(sites)


# ---------- раздел «Блокировка»: ссылки, взятые в работу ----------
# Единый список на всё приложение (не привязан к конкретному произведению
# файлом — но каждая запись хранит author_name/work_title как снимок на
# момент добавления, чтобы не потеряться, если автора/произведение потом
# удалят из мониторинга).
# Единый список на всё приложение (не привязан к конкретному произведению
# файлом — но каждая запись хранит author_name/work_title как снимок на
# момент добавления, чтобы не потеряться, если автора/произведение потом
# удалят из мониторинга).
#
# Общего единого «Статуса» дела больше нет — вместо одного поля три
# отдельных исхода по трём разным этапам процесса, у каждого свой набор
# одинаковых вариантов (APPEAL_DECISIONS):
#   1. claim_decision         — решение по досудебной претензии
#   2. first_appeal_decision  — решение по первому обращению (в Мосгорсуд и РКН)
#   3. repeat_appeal_decision — решение по повторному обращению
# Пустое значение = «ещё не определено» (сознательно нет отдельного «в
# работе» — это и есть его смысл).
APPEAL_DECISIONS = ["", "заблокировано", "отклонено", "нет реакции"]

# Типовые ответчики (хостинг/CDN-провайдеры) — для подсказки в интерфейсе,
# поле остаётся свободным текстом, это не жёсткий список.
COMMON_DEFENDANTS = ["Cloudflare, Inc.", "Bluehost Inc", "Godaddy.com, LLC", "Korea Telecom"]

DEFAULT_BLOCKING_CASE_FIELDS = {
    "discovered_at": "",        # дата обнаружения нарушения (заполняется вручную сотрудником)
    "presence_google": False,   # наличие в поисковой выдаче Google
    "presence_yandex": False,   # наличие в поисковой выдаче Яндекс
    "defendant": "",            # ответчик (хостинг-провайдер: Cloudflare, Bluehost, GoDaddy, Korea Telecom и т.п.)
    "defendant_email": "",      # email ответчика/хостинга — куда направлять жалобу
    "defendant_address": "",    # адрес регистрации + полное наименование ответчика (билингвально, вручную или
                                 # автоматически из RDAP, если провайдер публикует) — для заявления в суд
    "ip_address": "",           # IP-адрес сайта/сервера
    "claim_date": "",          # дата претензии администратору сайта
    "claim_decision": "",       # решение по претензии — один из APPEAL_DECISIONS
    "court_ruling_number": "",  # номер определения Мосгорсуда
    "court_ruling_date": "",    # дата определения Мосгорсуда
    "block_date": "",           # дата фактической блокировки
    "repeat_ruling": "",        # повторное решение (если ссылка всплыла на другом домене)
    "google_dmca_filed_at": "",  # дата отправки жалобы в Google DMCA (форма заполняется вручную, дата — тоже)
    # Avito больше не отдельные поля — как и VK/YouTube/Telegram/Instagram/
    # Facebook, обращение по нему теперь просто одна из записей в
    # other_complaints (см. ниже), никакого специального положения у него
    # больше нет.
    "other_complaints": [],  # список записей [{id, filed_at, method, notes}, ...] — сколько угодно обращений на разные сторонние площадки (не входящие в готовый список), не одно на дело
    "rkn_number": "",           # номер обращения в Роскомнадзор
    "rkn_filed_at": "",         # дата подачи обращения в РКН (первого)
    "repeat_petition_filed_at": "",  # дата повторной подачи заявления в МГС
    "repeat_rkn_filed_at": "",       # дата повторного обращения в РКН
    "first_appeal_decision": "",   # решение по первому обращению (МГС + РКН) — один из APPEAL_DECISIONS
    "repeat_appeal_decision": "",  # решение по повторному обращению — один из APPEAL_DECISIONS
    "notes": "",
    "petition_filed_at": "",    # дата фактической подачи заявления в суд по этой ссылке (ставится вручную)
    "link_check_interval": "day",  # как часто повторять проверку после первой: hour/day/week/month
    "link_checked_at": "",      # unix-время последней проверки доступности ссылки (пусто — ещё не проверялась)
    "link_status": "",          # "доступна" / "недоступна" — результат последней проверки
    "needs_resend": False,      # ссылка снова доступна (после заявления или после блокировки) — нужно действие
}


def load_blocking_cases():
    _ensure_files()
    with _lock:
        with open(BLOCKING_CASES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_blocking_cases(cases):
    _ensure_files()
    with _lock:
        with open(BLOCKING_CASES_FILE, "w", encoding="utf-8") as f:
            json.dump(cases, f, ensure_ascii=False, indent=2)


def get_blocking_case(case_id):
    for c in load_blocking_cases():
        if c["id"] == case_id:
            return c
    return None


def add_blocking_case(case):
    """Возвращает добавленное дело, либо None, если дело с такой же
    (нормализованной) ссылкой уже есть в блокировке ПОД ТЕМ ЖЕ САМЫМ
    ПРОИЗВЕДЕНИЕМ (work_id).

    Раньше уникальность была глобальной — одна и та же ссылка не могла
    быть добавлена дважды вообще нигде в системе. Оказалось, это мешает
    в реальных случаях: например, одна складчина-страница легально
    продаёт сразу несколько разных курсов одного автора (или даже разных
    авторов) — такую ссылку нужно отслеживать отдельно под каждым из
    них, это не дубль, а нарушение сразу нескольких произведений (см.
    заметку разработки, 03.09). Если у одного из двух дел (нового или
    уже существующего) work_id не указан вообще — не можем надёжно
    определить, «то же самое произведение или нет», подстраховываемся и
    считаем дублем (прежнее, более строгое поведение)."""
    with _lock:
        cases = load_blocking_cases()
        new_norm = _normalize_url_for_dedup(case.get("url"))
        new_work_id = case.get("work_id")
        for existing in cases:
            if _normalize_url_for_dedup(existing.get("url")) != new_norm:
                continue
            existing_work_id = existing.get("work_id")
            if not new_work_id or not existing_work_id or new_work_id == existing_work_id:
                return None
        case = dict(DEFAULT_BLOCKING_CASE_FIELDS, **case)
        case["id"] = str(uuid.uuid4())[:8]
        cases.append(case)
        save_blocking_cases(cases)
        return case


def update_blocking_case(case_id, patch):
    with _lock:
        cases = load_blocking_cases()
        updated = None
        for c in cases:
            if c["id"] == case_id:
                c.update(patch)
                updated = c
                break
        save_blocking_cases(cases)
        return updated


def add_other_complaint_entry(case_id, entry):
    """Добавляет одну запись в список «Другое» (обращения на сторонние
    площадки, не входящие в готовый список — Avito/Google) — сколько
    угодно записей на одно дело, не одна на дело, как было раньше."""
    with _lock:
        cases = load_blocking_cases()
        for c in cases:
            if c["id"] == case_id:
                c.setdefault("other_complaints", []).append(entry)
                save_blocking_cases(cases)
                return c
        return None


def delete_other_complaint_entry(case_id, entry_id):
    with _lock:
        cases = load_blocking_cases()
        for c in cases:
            if c["id"] == case_id:
                before = len(c.get("other_complaints", []))
                c["other_complaints"] = [e for e in c.get("other_complaints", []) if e.get("id") != entry_id]
                if len(c["other_complaints"]) == before:
                    return None  # такой записи не было — ничего не менялось
                save_blocking_cases(cases)
                return c
        return None


def delete_blocking_case(case_id):
    with _lock:
        cases = [c for c in load_blocking_cases() if c["id"] != case_id]
        save_blocking_cases(cases)
        for shot in get_case_screenshots(case_id):
            delete_screenshot(shot["id"])


# ---------- архив отчётов (дела, вошедшие в помесячный отчёт, уходят сюда из активной таблицы) ----------
def load_report_archive():
    _ensure_files()
    with _lock:
        with open(REPORT_ARCHIVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_report_archive(entries):
    _ensure_files()
    with _lock:
        with open(REPORT_ARCHIVE_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)


def archive_reported_cases(cases, year, month):
    """Переносит дела из активной таблицы блокировки в архив отчётов —
    вызывается сразу после того, как по ним построен помесячный отчёт.
    Скриншоты НЕ удаляются (в отличие от delete_blocking_case) — они
    остаются доступны по тому же case_id, просто дело больше не
    отображается в активной таблице «Блокировка»."""
    with _lock:
        archive = load_report_archive()
        now = time.time()
        for c in cases:
            entry = dict(c)
            entry["archived_at"] = now
            entry["report_year"] = year
            entry["report_month"] = month
            archive.append(entry)
        save_report_archive(archive)

        archived_ids = {c["id"] for c in cases}
        remaining = [c for c in load_blocking_cases() if c["id"] not in archived_ids]
        save_blocking_cases(remaining)


def get_report_archive_for_author(author_name):
    return sorted(
        (e for e in load_report_archive() if e.get("author_name") == author_name),
        key=lambda e: e.get("archived_at", 0),
        reverse=True,
    )


def restore_archived_case(case_id):
    """Обратная операция к archive_reported_cases — на случай, если
    завершили и заархивировали не тот месяц по ошибке. Возвращает
    восстановленное дело или None, если в архиве такого нет."""
    with _lock:
        archive = load_report_archive()
        entry = None
        remaining_archive = []
        for e in archive:
            if e["id"] == case_id and entry is None:
                entry = e
                continue
            remaining_archive.append(e)
        if entry is None:
            return None
        save_report_archive(remaining_archive)

        restored = {k: v for k, v in entry.items() if k not in ("archived_at", "report_year", "report_month")}
        cases = load_blocking_cases()
        cases.append(restored)
        save_blocking_cases(cases)
        return restored


def update_report_archive_entry(case_id, patch):
    """Точечно обновляет поля уже заархивированной записи, НЕ перенося её
    обратно в активную таблицу — используется фоновым мониторингом ссылок
    (см. jobs.py, _check_due_archived_cases_once), чтобы отмечать
    результат каждой проверки (link_status/link_checked_at) даже для
    дел, которые уже перенесены в архив отчётов. Если ссылка окажется
    снова доступна — переносом обратно в «Блокировку» занимается
    restore_archived_case, эта функция только фиксирует факт проверки."""
    with _lock:
        archive = load_report_archive()
        for e in archive:
            if e["id"] == case_id:
                e.update(patch)
                save_report_archive(archive)
                return e
        return None


# ---------- прогресс пакетного поиска (кнопка «Искать по всем активным») ----------
# Хранится на диске, а не только в памяти процесса (в отличие от jobs.py) —
# иначе при перезапуске сервера (обновление кода, падение, штатный деплой)
# посреди большого пакетного запуска не было бы способа узнать, что уже
# успело обработаться, а что нет, и пришлось бы начинать заново с нуля.
def save_bulk_search_batch(batch):
    with _lock:
        with open(BULK_SEARCH_BATCH_FILE, "w", encoding="utf-8") as f:
            json.dump(batch, f, ensure_ascii=False, indent=2)


def load_bulk_search_batch():
    if not os.path.exists(BULK_SEARCH_BATCH_FILE):
        return None
    with _lock:
        with open(BULK_SEARCH_BATCH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def start_bulk_search_batch(batch_id, work_ids, scope_label):
    save_bulk_search_batch({
        "id": batch_id,
        "scope_label": scope_label,  # для интерфейса: "всем активным" или "автору Иванов"
        "started_at": time.time(),
        "work_ids": work_ids,
        "work_status": {},  # work_id -> {"status": "done"/"error"/"cancelled", "finished_at": ...}
    })


def mark_bulk_search_work_finished(batch_id, work_id, status):
    """Вызывается по завершении фоновой задачи каждого произведения — если
    это не та партия, что сейчас записана (например, запустили новую поверх
    старой незавершённой), тихо ничего не делает."""
    with _lock:
        batch = load_bulk_search_batch()
        if not batch or batch.get("id") != batch_id:
            return
        batch.setdefault("work_status", {})[work_id] = {"status": status, "finished_at": time.time()}
        with open(BULK_SEARCH_BATCH_FILE, "w", encoding="utf-8") as f:
            json.dump(batch, f, ensure_ascii=False, indent=2)


def clear_bulk_search_batch():
    if os.path.exists(BULK_SEARCH_BATCH_FILE):
        os.remove(BULK_SEARCH_BATCH_FILE)


# ---------- скриншоты по делу блокировки (фиксация нарушения) ----------
def load_screenshots():
    _ensure_files()
    with _lock:
        with open(SCREENSHOTS_META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_screenshots(shots):
    _ensure_files()
    with _lock:
        with open(SCREENSHOTS_META_FILE, "w", encoding="utf-8") as f:
            json.dump(shots, f, ensure_ascii=False, indent=2)


def get_case_screenshots(case_id):
    return [s for s in load_screenshots() if s["case_id"] == case_id]


def get_screenshot(shot_id):
    for s in load_screenshots():
        if s["id"] == shot_id:
            return s
    return None


def add_screenshot(meta):
    with _lock:
        shots = load_screenshots()
        meta = dict(meta)
        meta["id"] = str(uuid.uuid4())[:8]
        shots.append(meta)
        save_screenshots(shots)
        return meta


def delete_screenshot(shot_id):
    with _lock:
        shot = get_screenshot(shot_id)
        shots = [s for s in load_screenshots() if s["id"] != shot_id]
        save_screenshots(shots)
        if shot:
            path = os.path.join(SCREENSHOTS_DIR, shot["stored_filename"])
            if os.path.exists(path):
                os.remove(path)
            html_filename = shot.get("html_filename")
            if html_filename:
                html_path = os.path.join(SCREENSHOTS_DIR, html_filename)
                if os.path.exists(html_path):
                    os.remove(html_path)


# ---------- документы автора (доверенности, подтверждение авторства и т.п.) ----------
DOCUMENT_TYPES = ["доверенность", "подтверждение авторства", "договор", "скан паспорта", "другое"]


def load_documents():
    _ensure_files()
    with _lock:
        with open(DOCUMENTS_META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_documents(docs):
    _ensure_files()
    with _lock:
        with open(DOCUMENTS_META_FILE, "w", encoding="utf-8") as f:
            json.dump(docs, f, ensure_ascii=False, indent=2)


def get_author_documents(author_id):
    return [d for d in load_documents() if d["author_id"] == author_id]


def get_document(doc_id):
    for d in load_documents():
        if d["id"] == doc_id:
            return d
    return None


def add_document(meta):
    with _lock:
        docs = load_documents()
        meta = dict(meta)
        meta["id"] = str(uuid.uuid4())[:8]
        docs.append(meta)
        save_documents(docs)
        return meta


def delete_document(doc_id):
    """Удаляет только метаданные — сам зашифрованный файл на диске удаляет
    вызывающий код через document_vault.delete_encrypted (storage.py не
    знает про шифрование, это забота app.py)."""
    with _lock:
        docs = [d for d in load_documents() if d["id"] != doc_id]
        save_documents(docs)


# ---------- документы сотрудника (доверенность от фирмы и т.п.) ----------
# Тот же принцип, что и документы автора (зашифрованное хранилище через
# document_vault.py), но ключ — username подающего заявления сотрудника,
# не author_id. У каждого сотрудника свой отдельный набор документов —
# они автоматически прикладываются к каждому заявлению, которое готовит
# именно этот сотрудник (см. petition-эндпоинт в app.py).
def load_employee_documents():
    _ensure_files()
    with _lock:
        with open(EMPLOYEE_DOCUMENTS_META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_employee_documents(docs):
    _ensure_files()
    with _lock:
        with open(EMPLOYEE_DOCUMENTS_META_FILE, "w", encoding="utf-8") as f:
            json.dump(docs, f, ensure_ascii=False, indent=2)


def get_employee_documents(username):
    return [d for d in load_employee_documents() if d["username"] == username]


def get_employee_document(doc_id):
    for d in load_employee_documents():
        if d["id"] == doc_id:
            return d
    return None


def add_employee_document(meta):
    with _lock:
        docs = load_employee_documents()
        meta = dict(meta)
        meta["id"] = str(uuid.uuid4())[:8]
        docs.append(meta)
        save_employee_documents(docs)
        return meta


def delete_employee_document(doc_id):
    with _lock:
        docs = [d for d in load_employee_documents() if d["id"] != doc_id]
        save_employee_documents(docs)


# ---------- настройки (пока только шаблон жалобы, но задел на будущее) ----------
DEFAULT_COMPLAINT_TEMPLATE = {
    "subject": "Жалоба на нарушение авторских прав — {work_title}",
    "body": (
        "Здравствуйте,\n\n"
        "Обращаемся в связи с обнаруженным на сайте {url} незаконным "
        "распространением материалов, правообладателем которых является {author}.\n\n"
        "IP-адрес сайта: {ip}\n\n"
        "Просим удалить указанный контент или заблокировать доступ к нему "
        "в кратчайшие сроки, а также сообщить о принятых мерах.\n\n"
        "С уважением"
    ),
}


def load_settings():
    _ensure_files()
    if not os.path.exists(SETTINGS_FILE):
        return {}
    with _lock:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_settings(settings):
    _ensure_files()
    with _lock:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)


# ---------- произвольные шаблоны, добавляемые вручную через интерфейс ----------
# В отличие от DEFAULT_TEMPLATES (Avito) и complaint_template (претензия
# хостингу) — у этих нет привязки к конкретной кнопке отправки в интерфейсе
# (для площадок вроде VK/Instagram/YouTube автоматической отправки нет,
# см. openOtherComplaintsModal во frontend/app.js). Это просто библиотека
# заготовленного текста, который можно скопировать вручную при заполнении
# официальной формы жалобы такой площадки.
def load_custom_templates():
    return load_settings().get("custom_templates", [])


def create_custom_template(name, subject, body):
    with _lock:
        settings = load_settings()
        templates = settings.get("custom_templates", [])
        template = {"id": str(uuid.uuid4())[:8], "name": name, "subject": subject, "body": body}
        templates.append(template)
        settings["custom_templates"] = templates
        save_settings(settings)
        return template


def update_custom_template(template_id, name, subject, body):
    with _lock:
        settings = load_settings()
        templates = settings.get("custom_templates", [])
        for t in templates:
            if t["id"] == template_id:
                t["name"], t["subject"], t["body"] = name, subject, body
                save_settings(settings)
                return t
        return None


def delete_custom_template(template_id):
    with _lock:
        settings = load_settings()
        templates = settings.get("custom_templates", [])
        new_templates = [t for t in templates if t["id"] != template_id]
        if len(new_templates) == len(templates):
            return False
        settings["custom_templates"] = new_templates
        save_settings(settings)
        return True


def get_complaint_template():
    """Возвращает текущий шаблон жалобы — сохранённый пользователем, если
    он есть, иначе значение по умолчанию. Всегда оба поля (subject, body),
    даже если сохранена только часть — вторую часть достраиваем из
    умолчания, чтобы не оставлять тему или текст письма пустыми."""
    saved = load_settings().get("complaint_template", {})
    return {
        "subject": saved.get("subject") or DEFAULT_COMPLAINT_TEMPLATE["subject"],
        "body": saved.get("body") or DEFAULT_COMPLAINT_TEMPLATE["body"],
        "is_custom": bool(saved.get("subject") or saved.get("body")),
    }


def save_complaint_template(subject, body):
    with _lock:
        settings = load_settings()
        settings["complaint_template"] = {"subject": subject, "body": body}
        _ensure_files()
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)


def reset_complaint_template():
    with _lock:
        settings = load_settings()
        settings.pop("complaint_template", None)
        _ensure_files()
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)


# Реквизиты самой юрфирмы (шапка «Акта выполненных работ») — единые на всё
# приложение, не привязаны к конкретному автору/заказчику, поэтому хранятся
# отдельно от карточки автора, но по тому же принципу, что и шаблон жалобы.
DEFAULT_FIRM_LETTERHEAD = {
    "name": "",
    "email": "",
    "phone": "",
    "address": "",
}


def get_firm_letterhead():
    saved = load_settings().get("firm_letterhead", {})
    return {**DEFAULT_FIRM_LETTERHEAD, **saved}


def save_firm_letterhead(letterhead):
    with _lock:
        settings = load_settings()
        settings["firm_letterhead"] = {
            "name": letterhead.get("name", ""),
            "email": letterhead.get("email", ""),
            "phone": letterhead.get("phone", ""),
            "address": letterhead.get("address", ""),
        }
        _ensure_files()
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)


class _SafeFormatDict(dict):
    """Если в шаблоне пользователь опечатался в имени плейсхолдера (или
    сослался на несуществующий) — не роняем всё письмо ошибкой, просто
    оставляем «{опечатка}» как есть в тексте, это подскажет, что не так,
    и не потеряет остальной текст письма."""
    def __missing__(self, key):
        return "{" + key + "}"


def render_complaint_template(template_str, values):
    return template_str.format_map(_SafeFormatDict(values))


# ---------- ручные правки к аналитике (только admin) ----------
def load_analytics_overrides():
    """Возвращает {"detected": {"2026-08": 15, ...}, "blocked": {...}} —
    ручные поправки к автоматически посчитанным цифрам, если подсчёт
    что-то не учёл. Пустой словарь, если правок ещё не делали ни разу —
    файл создаётся лениво, только при первом сохранении, как и settings.json."""
    _ensure_files()
    if not os.path.exists(ANALYTICS_OVERRIDES_FILE):
        return {"detected": {}, "blocked": {}}
    with _lock:
        with open(ANALYTICS_OVERRIDES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    data.setdefault("detected", {})
    data.setdefault("blocked", {})
    return data


def set_analytics_override(metric, month, value):
    """value=None — убрать поправку для этого месяца (вернуться к
    автоматическому подсчёту)."""
    if metric not in ("detected", "blocked"):
        raise ValueError(f"Неизвестная метрика: {metric}")
    with _lock:
        data = load_analytics_overrides()
        if value is None:
            data[metric].pop(month, None)
        else:
            data[metric][month] = value
        _ensure_files()
        with open(ANALYTICS_OVERRIDES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return data


# ---------- журнал действий (кто что сделал) ----------
# Работает только вместе с включённой аутентификацией (APP_USERS в .env) —
# без именных пользователей «кто» всё равно неизвестно, поэтому пишем только
# когда есть реальное имя.
AUDIT_LOG_MAX_ENTRIES = 5000  # чтобы файл не рос бесконечно на очень старых установках


def log_action(username, action, details=""):
    if not username:
        return
    _ensure_files()
    with _lock:
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            entries = json.load(f)
        entries.append({
            "ts": time.time(),
            "username": username,
            "action": action,
            "details": details,
        })
        if len(entries) > AUDIT_LOG_MAX_ENTRIES:
            entries = entries[-AUDIT_LOG_MAX_ENTRIES:]
        with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)


def load_audit_log(limit=200):
    _ensure_files()
    with _lock:
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            entries = json.load(f)
    return list(reversed(entries))[:limit]


# ---------- журнал отправок (претензии, жалобы Avito/Google, заявления) ----------
# Отдельный от общего журнала действий (тот — общий для всех действий в
# приложении, доступен только admin уже сейчас; этот — специализированный,
# именно под «кто когда что отправил» по конкретному делу, тоже только
# admin). Редакторы по-прежнему сами отправляют претензии/жалобы/заявления
# и видят сами даты в таблице как обычно — этот журнал просто
# дополнительно фиксирует те же события в одном месте для admin.
COMPLAINT_SEND_LOG_MAX_ENTRIES = 5000

COMPLAINT_SEND_TYPES = {
    "claim": "Претензия администратору сайта",
    "petition": "Заявление в суд (первое)",
    "repeat_petition": "Заявление в суд (повторное)",
    "rkn": "Обращение в РКН (первое)",
    "repeat_rkn": "Обращение в РКН (повторное)",
    "google_dmca": "Жалоба в Google DMCA",
    "avito": "Жалоба на объявление Avito",
    "other": "Другое (произвольный канал)",
}


def add_complaint_send_log_entry(entry):
    _ensure_files()
    with _lock:
        with open(COMPLAINT_SEND_LOG_FILE, "r", encoding="utf-8") as f:
            entries = json.load(f)
        entries.append({
            "ts": time.time(),
            "username": entry.get("username", ""),
            "type": entry.get("type", ""),
            "case_id": entry.get("case_id", ""),
            "url": entry.get("url", ""),
            "author_name": entry.get("author_name", ""),
            "work_title": entry.get("work_title", ""),
            "date_value": entry.get("date_value", ""),
            "channel": entry.get("channel", ""),
        })
        if len(entries) > COMPLAINT_SEND_LOG_MAX_ENTRIES:
            entries = entries[-COMPLAINT_SEND_LOG_MAX_ENTRIES:]
        with open(COMPLAINT_SEND_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)


def load_complaint_send_log(limit=500):
    _ensure_files()
    with _lock:
        with open(COMPLAINT_SEND_LOG_FILE, "r", encoding="utf-8") as f:
            entries = json.load(f)
    return list(reversed(entries))[:limit]


# ---------- пользователи (динамические, с ролями) ----------
def load_users():
    _ensure_files()
    with _lock:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_users(users):
    _ensure_files()
    with _lock:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)


def get_user_by_username(username):
    for u in load_users():
        if u["username"] == username:
            return u
    return None


def get_user_by_id(user_id):
    for u in load_users():
        if u["id"] == user_id:
            return u
    return None


def create_user(username, password_hash, role, created_by=None):
    with _lock:
        users = load_users()
        if any(u["username"] == username for u in users):
            raise ValueError("Пользователь с таким именем уже существует")
        user = {
            "id": str(uuid.uuid4())[:8],
            "username": username,
            "password_hash": password_hash,
            "role": role,
            "created_at": time.time(),
            "created_by": created_by,
        }
        users.append(user)
        save_users(users)
        return user


def update_user_role(user_id, role):
    with _lock:
        users = load_users()
        updated = None
        for u in users:
            if u["id"] == user_id:
                u["role"] = role
                updated = u
                break
        save_users(users)
        return updated


def update_user_password(user_id, password_hash):
    """Смена пароля напрямую по id — используется reset_admin_password.py
    (аварийное восстановление доступа), не завязана на текущую сессию,
    в отличие от обычной смены пароля пользователем самому себе."""
    with _lock:
        users = load_users()
        updated = None
        for u in users:
            if u["id"] == user_id:
                u["password_hash"] = password_hash
                updated = u
                break
        save_users(users)
        return updated


def count_admins():
    return sum(1 for u in load_users() if u["role"] == "admin")


def delete_user(user_id):
    with _lock:
        users = [u for u in load_users() if u["id"] != user_id]
        save_users(users)


# ---------- ссылки-приглашения (одноразовые, с привязанной ролью) ----------
INVITE_TTL_SECONDS = 7 * 24 * 3600  # неделя


def load_invites():
    _ensure_files()
    with _lock:
        with open(INVITES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_invites(invites):
    _ensure_files()
    with _lock:
        with open(INVITES_FILE, "w", encoding="utf-8") as f:
            json.dump(invites, f, ensure_ascii=False, indent=2)


def create_invite(role, created_by):
    with _lock:
        invites = load_invites()
        invite = {
            "token": uuid.uuid4().hex,
            "role": role,
            "created_by": created_by,
            "created_at": time.time(),
            "expires_at": time.time() + INVITE_TTL_SECONDS,
            "used": False,
            "used_by": None,
        }
        invites.append(invite)
        save_invites(invites)
        return invite


def get_invite(token):
    for inv in load_invites():
        if inv["token"] == token:
            return inv
    return None


def is_invite_valid(invite):
    if invite is None:
        return False
    if invite["used"]:
        return False
    if time.time() > invite["expires_at"]:
        return False
    return True


def mark_invite_used(token, used_by):
    with _lock:
        invites = load_invites()
        for inv in invites:
            if inv["token"] == token:
                inv["used"] = True
                inv["used_by"] = used_by
                break
        save_invites(invites)


def delete_invite(token):
    with _lock:
        invites = [i for i in load_invites() if i["token"] != token]
        save_invites(invites)


# ---------- временные разрешения на просмотр чувствительных документов автора ----------
# Паспорт, СНИЛС, скан доверенности и т.п. — по умолчанию видит только admin
# (см. author_personal_data.py, document_vault.py). Разрешение даёт
# конкретному сотруднику ВРЕМЕННЫЙ доступ на ПРОСМОТР (не на скачивание
# исходного файла — это по-прежнему только у admin, см. app.py) — либо по
# одному автору, либо по всем сразу (scope). Каждая выдача и отзыв
# фиксируются в журнале действий (см. app.py).
GRANT_DURATION_PRESETS = {"1d": 1, "3d": 3, "7d": 7}  # быстрые варианты в интерфейсе, в днях


def load_document_access_grants():
    _ensure_files()
    with _lock:
        with open(DOCUMENT_ACCESS_GRANTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_document_access_grants(grants):
    _ensure_files()
    with _lock:
        with open(DOCUMENT_ACCESS_GRANTS_FILE, "w", encoding="utf-8") as f:
            json.dump(grants, f, ensure_ascii=False, indent=2)


def create_document_access_grant(username, scope, author_id, granted_by, expires_at):
    """scope: "all" (все авторы) или "author" (только один, тогда author_id
    обязателен). expires_at — unix-время окончания действия, обязателен —
    бессрочных разрешений на такие данные сознательно не бывает."""
    with _lock:
        grants = load_document_access_grants()
        grant = {
            "id": str(uuid.uuid4())[:8],
            "username": username,
            "scope": scope,
            "author_id": author_id if scope == "author" else None,
            "granted_by": granted_by,
            "granted_at": time.time(),
            "expires_at": expires_at,
            "revoked": False,
            "revoked_at": None,
        }
        grants.append(grant)
        save_document_access_grants(grants)
        return grant


def revoke_document_access_grant(grant_id):
    with _lock:
        grants = load_document_access_grants()
        for g in grants:
            if g["id"] == grant_id:
                g["revoked"] = True
                g["revoked_at"] = time.time()
                save_document_access_grants(grants)
                return g
        return None


# ---------- временные разрешения на редактирование справочника «Поиск по
# сайтам» ----------
# Раньше справочник сайтов мог редактировать только admin — неудобно для
# команд, где этим занимается конкретный сотрудник, а не единственный
# администратор (см. заметку разработки, 03.09). Устроено так же, как и
# разрешения на документы автора выше, но без привязки к конкретному
# автору — справочник сайтов общий на всё приложение, не по авторам.
def load_site_access_grants():
    _ensure_files()
    with _lock:
        with open(SITE_ACCESS_GRANTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_site_access_grants(grants):
    _ensure_files()
    with _lock:
        with open(SITE_ACCESS_GRANTS_FILE, "w", encoding="utf-8") as f:
            json.dump(grants, f, ensure_ascii=False, indent=2)


def create_site_access_grant(username, granted_by, expires_at):
    with _lock:
        grants = load_site_access_grants()
        grant = {
            "id": str(uuid.uuid4())[:8],
            "username": username,
            "granted_by": granted_by,
            "granted_at": time.time(),
            "expires_at": expires_at,
            "revoked": False,
            "revoked_at": None,
        }
        grants.append(grant)
        save_site_access_grants(grants)
        return grant


def revoke_site_access_grant(grant_id):
    with _lock:
        grants = load_site_access_grants()
        for g in grants:
            if g["id"] == grant_id:
                g["revoked"] = True
                g["revoked_at"] = time.time()
                save_site_access_grants(grants)
                return g
        return None


def has_active_site_access_grant(username):
    now = time.time()
    for g in load_site_access_grants():
        if g["username"] != username or g.get("revoked"):
            continue
        if g["expires_at"] and g["expires_at"] < now:
            continue
        return True
    return False


def has_active_document_grant(username, author_id):
    """Есть ли у этого сотрудника прямо сейчас действующее разрешение на
    просмотр документов именно этого автора (по имени или по scope="all")."""
    now = time.time()
    for g in load_document_access_grants():
        if g["username"] != username or g.get("revoked"):
            continue
        if g["expires_at"] and g["expires_at"] < now:
            continue
        if g["scope"] == "all" or (g["scope"] == "author" and g["author_id"] == author_id):
            return True
    return False


def list_active_grants_for_username(username):
    """Для самого сотрудника — что именно ему сейчас доступно (для фронтенда,
    чтобы понять, какие иконки документов показывать в дереве авторов)."""
    now = time.time()
    result = []
    for g in load_document_access_grants():
        if g["username"] != username or g.get("revoked"):
            continue
        if g["expires_at"] and g["expires_at"] < now:
            continue
        result.append({"scope": g["scope"], "author_id": g["author_id"], "expires_at": g["expires_at"]})
    return result



# ---------- отчёт сравнения выдачи Яндекса HTML / XML (режим compare) ----------
YANDEX_COMPARE_FILE = os.path.join(DATA_DIR, "yandex_compare_log.json")
YANDEX_COMPARE_MAX = 300


def load_yandex_compare():
    with _lock:
        if not os.path.exists(YANDEX_COMPARE_FILE):
            return []
        try:
            with open(YANDEX_COMPARE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return []


def append_yandex_compare(entry):
    with _lock:
        entries = load_yandex_compare()
        entries.append(entry)
        entries = entries[-YANDEX_COMPARE_MAX:]
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(YANDEX_COMPARE_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False)


def update_site_fields(site_id, patch):
    """Точечное обновление полей сайта (статус последней проверки и т.п.)
    под общей блокировкой — без перезаписи остальных полей."""
    with _lock:
        sites = load_sites()
        for s in sites:
            if s.get("id") == site_id:
                s.update(patch)
                save_sites(sites)
                return s
        return None


def update_other_complaint_entry(case_id, entry_id, patch):
    """Точечное изменение одной записи «Жалобы» (например, дата удаления
    ссылки из выдачи Google). Ищет и в активных делах, и в архиве."""
    with _lock:
        cases = load_blocking_cases()
        for c in cases:
            if c.get("id") == case_id:
                for e in c.get("other_complaints") or []:
                    if e.get("id") == entry_id:
                        e.update(patch)
                        save_blocking_cases(cases)
                        return c
                return None
        archive = load_report_archive()
        for c in archive:
            if c.get("id") == case_id:
                for e in c.get("other_complaints") or []:
                    if e.get("id") == entry_id:
                        e.update(patch)
                        save_report_archive(archive)
                        return c
        return None
