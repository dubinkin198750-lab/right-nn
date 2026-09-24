"""Оркестрация источников поиска.

У Avito и Telegram нет открытого публичного API для поиска объявлений/постов
по всему сервису (Avito API — только для работы со своими объявлениями,
Telegram не индексирует публичные каналы через официальный поисковый API).
Поэтому «поиск по Avito» и «поиск по Telegram» реализован как обычный
веб-поиск (через Yandex и/или Google) с ограничением на конкретный сайт —
`site:avito.ru` / `site:t.me`. Это тот же принцип, каким реальные ссылки на
Avito находились и в исходном сценарии (через обычную поисковую выдачу).

У такого способа есть слабое место: если по запросу почти нет точных
совпадений (а для пиратского контента на Avito это почти всегда так — это
маркетплейс товаров и услуг, не площадка для раздач), Яндекс всё равно
старается что-то вернуть и подсовывает произвольные категорийные страницы
сайта («мотоциклы», «стройматериалы» и т.п.), никак не связанные с запросом.
Поэтому для avito/telegram результатов дополнительно применяется простая
проверка релевантности — среди значимых слов запроса хотя бы одно должно
реально встретиться в заголовке/описании/ссылке, иначе результат
отбрасывается ещё до общего фильтра по ключевым словам произведения.
"""
import re
import time

from . import yandex_search, google_search, duckduckgo_search
from . import vk_search, torznab_search

SOURCE_LABELS = {
    "yandex": "Яндекс",
    "google": "Google",
    "duckduckgo": "DuckDuckGo",
    "avito": "Avito (через сайт-фильтр)",
    "vk": "VK: записи",
    "vk_video": "VK: видео",
    "torrents": "Торренты",
    "telegram": "Telegram (через сайт-фильтр)",
}

SITE_RESTRICTED_SOURCES = {"avito", "telegram"}
_MIN_SIGNIFICANT_WORD_LEN = 3
INTER_TASK_DELAY_SEC = 1  # пауза между последовательными задачами к одному
# и тому же API — тесты могут обнулить эту переменную, чтобы не ждать реально


def _significant_words(base_query):
    """Значимые слова запроса — без операторов (site:, кавычки, +), без
    коротких служебных слов (предлоги и т.п.)."""
    cleaned = re.sub(r"site:\S+", "", base_query)
    cleaned = cleaned.replace('"', " ").replace("+", " ")
    words = re.findall(r"[а-яёa-z0-9]+", cleaned.lower())
    return [w for w in words if len(w) >= _MIN_SIGNIFICANT_WORD_LEN]


def _looks_relevant(item, significant_words):
    if not significant_words:
        return True  # нечего проверять — не отбрасываем
    haystack = f"{item.get('title', '')} {item.get('description', '')} {item.get('url', '')}".lower()
    for w in significant_words:
        # для слов длиннее ~5 букв сравниваем по основе (первые 5 символов),
        # а не целиком — иначе "белоусова" не совпадёт с "белоусовой"/"белоусову"
        # и т.п. падежными формами в реальном тексте объявления
        stem = w[:5] if len(w) > 5 else w
        if stem in haystack:
            return True
    return False


def _normalize_queries(base_query):
    """base_query — строка (старый формат, одно произведение = один запрос)
    или список строк (новый формат — несколько вариантов формулировки за
    один прогон). Всегда возвращает непустой список строк."""
    if isinstance(base_query, str):
        queries = [base_query]
    else:
        queries = list(base_query or [])
    queries = [q.strip() for q in queries if isinstance(q, str) and q.strip()]
    return queries or [""]


def build_tasks(base_query, sources):
    """sources — dict {"yandex": bool, "google": bool, "duckduckgo": bool, "avito": bool, "telegram": bool}.
    base_query — строка или список строк (см. _normalize_queries).
    Возвращает список задач (engine, query_text, source_label)."""
    queries = _normalize_queries(base_query)
    tasks = []
    yandex_on = sources.get("yandex", False)
    google_on = sources.get("google", False)
    duckduckgo_on = sources.get("duckduckgo", False)

    for q in queries:
        if yandex_on:
            tasks.append(("yandex", q, SOURCE_LABELS["yandex"]))
        if google_on:
            tasks.append(("google", q, SOURCE_LABELS["google"]))
        if duckduckgo_on:
            tasks.append(("duckduckgo", q, SOURCE_LABELS["duckduckgo"]))

        for key, site in (("avito", "site:avito.ru"), ("telegram", "site:t.me")):
            if not sources.get(key, False):
                continue
            site_query = f"{q} {site}"
            # используем те же движки, что включены для обычного поиска;
            # если ни один явно не выбран — по умолчанию через Яндекс
            used_any = False
            if yandex_on:
                tasks.append(("yandex", site_query, SOURCE_LABELS[key]))
                used_any = True
            if google_on:
                tasks.append(("google", site_query, SOURCE_LABELS[key]))
                used_any = True
            if duckduckgo_on:
                tasks.append(("duckduckgo", site_query, SOURCE_LABELS[key]))
                used_any = True
            if not used_any:
                tasks.append(("yandex", site_query, SOURCE_LABELS[key]))

        # Новые самостоятельные источники (обновление 23.09) — со своими
        # API, не через поисковик. По умолчанию выключены.
        for key in ("vk", "vk_video", "torrents"):
            if sources.get(key, False):
                tasks.append((key, q, SOURCE_LABELS[key]))

    if not tasks:
        # ничего не выбрано — по умолчанию обычный поиск через Яндекс
        tasks.append(("yandex", queries[0], SOURCE_LABELS["yandex"]))

    return tasks


def source_available(engine):
    """(доступен ли источник, причина если нет). Google без ключа при
    настроенном Яндексе НЕ выдаёт выдуманных демо-результатов — они
    допустимы только в полностью демонстрационной установке (ни одного
    ключа), где ими никто не будет пользоваться всерьёз."""
    if engine == "google" and not is_google_configured() and yandex_search.is_configured():
        return False, "не настроен (нет ключа Google; демо-результаты отключены)"
    if engine == "vk" and not vk_search.is_configured():
        return False, "не настроен (нет VK_SERVICE_TOKEN)"
    if engine == "vk_video" and not vk_search.is_video_configured():
        return False, "не настроен (нет VK_USER_TOKEN)"
    if engine == "torrents" and not torznab_search.is_configured():
        return False, "не настроен (нет TORZNAB_URL)"
    return True, ""


def run_search(base_query, pages, sources, progress_cb=None, should_stop=None, report=None):
    """Выполняет поиск по всем включённым источникам и всем вариантам
    запроса (если их несколько), помечает каждый результат полем "source",
    объединяет в один список. Результаты с одной и той же ссылкой,
    найденные разными вариантами запроса, дедуплицируются — ссылка
    засчитывается один раз, за первым вариантом запроса, которым нашлась.
    should_stop — необязательный колбэк без аргументов: если возвращает True,
    поиск останавливается досрочно (между задачами/страницами) и возвращает
    то, что успело накопиться, вместо ошибки или зависания.
    report — необязательный словарь: если передан, в него записывается
    итог по каждому источнику {метка: {"status", "found", "errors", "tasks"}},
    чтобы было видно, какой источник что нашёл, какой не настроен и какой
    упал с ошибкой (раньше это было видно только когда падали все сразу).
    Возвращает (items, any_demo_mode)."""
    queries = _normalize_queries(base_query)
    multi = len(queries) > 1
    tasks = build_tasks(base_query, sources)
    all_items = []
    seen_urls = set()
    any_demo = False

    total_tasks = len(tasks)
    last_error = None
    failed_tasks = 0
    skipped_tasks = set()
    prev_engine = None
    for task_idx, (engine, query_text, source_label) in enumerate(tasks):
        if should_stop and should_stop():
            break
        if prev_engine == engine and task_idx > 0:
            # небольшая пауза между последовательными задачами к одному и
            # тому же API (например, между разными вариантами запроса) —
            # без этого несколько запросов подряд без остановки могут
            # вызвать замедление/таймауты на стороне API
            time.sleep(INTER_TASK_DELAY_SEC)
        if should_stop and should_stop():
            break  # проверяем и после паузы
        prev_engine = engine

        significant_words = _significant_words(query_text)

        def cb(page, total_pages, _idx=task_idx, _label=source_label, _q=query_text):
            if progress_cb:
                label = _label if not multi else f"{_label} — «{_q}»"
                progress_cb(_idx, total_tasks, page, total_pages, label)

        rep = None
        if report is not None:
            rep = report.setdefault(source_label, {"status": "ok", "found": 0, "errors": [], "tasks": 0})
            rep["tasks"] += 1
        available, reason = source_available(engine)
        if not available:
            if rep is not None:
                rep["status"] = "not_configured"
                if reason not in rep["errors"]:
                    rep["errors"].append(reason)
            skipped_tasks.add(task_idx)  # пропуск ненастроенного источника — не сбой прогона
            continue

        try:
            if engine == "vk":
                items, demo = vk_search.search_posts(query_text, pages, cb, should_stop=should_stop)
            elif engine == "vk_video":
                items, demo = vk_search.search_videos(query_text, pages, cb, should_stop=should_stop)
            elif engine == "torrents":
                items, demo = torznab_search.search(query_text, pages, cb, should_stop=should_stop)
            elif engine == "google":
                items, demo = google_search.search(query_text, pages, cb, should_stop=should_stop)
            elif engine == "duckduckgo":
                items, demo = duckduckgo_search.search(query_text, pages, cb, should_stop=should_stop)
            else:
                items, demo = yandex_search.search(query_text, pages, cb, should_stop=should_stop)
        except Exception as e:  # noqa — не роняем весь прогон из-за одного источника/запроса
            last_error = e
            failed_tasks += 1
            if rep is not None:
                rep["status"] = "error"
                msg = str(e)[:300]
                if msg not in rep["errors"]:
                    rep["errors"].append(msg)
            continue

        is_site_restricted = any(
            source_label == SOURCE_LABELS[key] for key in SITE_RESTRICTED_SOURCES
        )
        if is_site_restricted:
            items = [it for it in items if _looks_relevant(it, significant_words)]

        for it in items:
            if it.get("url") in seen_urls:
                continue
            seen_urls.add(it.get("url"))
            it["source"] = source_label
            all_items.append(it)
            if rep is not None:
                rep["found"] += 1
        any_demo = any_demo or demo

    if last_error and failed_tasks == total_tasks - len(skipped_tasks) and failed_tasks > 0:
        # вообще ни один источник/запрос не отработал — вероятная системная
        # проблема (ключ/лимиты/доступность API), стоит показать ошибку,
        # а не тихо вернуть пустой список, как будто просто ничего не нашлось
        raise last_error

    return all_items, any_demo


def is_google_configured():
    return google_search.is_configured()


def is_duckduckgo_configured():
    return duckduckgo_search.is_configured()
