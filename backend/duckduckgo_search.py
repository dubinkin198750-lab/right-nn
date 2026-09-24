"""Поиск через DuckDuckGo.

У DuckDuckGo нет официального публичного API для обычного веб-поиска (их
официальный API — Instant Answer API, отвечает только на короткие
"мгновенные ответы" вроде определений/фактов, не даёт органическую
поисковую выдачу). Единственный практический способ получить обычные
результаты — разобрать HTML статической (без JS) версии страницы
результатов, https://html.duckduckgo.com/html/ — так же поступают
большинство открытых инструментов для этой задачи.

Честная оговорка, аналогично 2ip.io и Avito в других частях приложения:
- Это НЕ официально поддерживаемый способ доступа, разметка страницы может
  измениться в любой момент без предупреждения и сломать разбор.
- Сообщество сообщает о блокировке уже примерно от ~30 запросов в минуту с
  одного IP — здесь сознательно взята более осторожная пауза между
  страницами, чем для Yandex Search API (там официальный ключ и лимиты
  предсказуемее).
- В отличие от Yandex/Google, здесь не нужен API-ключ вообще — is_configured()
  всегда возвращает True, «демо-режим из-за отсутствия ключа» тут просто
  неприменимое понятие.

Платный резерв (SerpApi, engine=duckduckgo — настоящий, документированный
движок именно DuckDuckGo, не просто «какой-то поиск», см.
https://serpapi.com/duckduckgo-search-api): если бесплатный скрейпинг
провалился на ВСЕХ страницах подряд (обычно это и значит, что сработала
блокировка) и задан ключ SERPAPI_KEY — автоматически переключаемся на
платный путь для того же запроса вместо того, чтобы поднимать ошибку.
Если бесплатный путь провалился только частично (часть страниц прошла) —
резерв НЕ включается, отдаём то, что уже получили, как и раньше: смешивать
результаты из двух разных источников в одном ответе было бы путаницей."""
import os
import re
import time
from urllib.parse import urlparse, parse_qs, unquote

import requests

SEARCH_URL = "https://html.duckduckgo.com/html/"
RESULTS_PER_PAGE = 30  # шаг офсета между страницами (см. параметр "s" ниже)
REQUEST_TIMEOUT = 15
PAGE_DELAY_SEC = 2  # осторожнее, чем у Yandex (там официальный ключ) — сообщество сообщает о блокировке от ~30 запросов/мин с одного IP

SERPAPI_URL = "https://serpapi.com/search"
SERPAPI_RESULTS_PER_PAGE = 30  # тот же шаг, что и у бесплатного пути — для одинаковой логики страниц выше

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


class DuckDuckGoSearchError(RuntimeError):
    pass


def is_configured():
    """Ключ/токен не нужен вообще — скрейпинг публичной страницы. Всегда
    True, «демо-режим из-за отсутствия ключа» здесь неприменимое понятие
    (в отличие от Yandex/Google)."""
    return True


def is_serpapi_fallback_configured():
    """Платный резерв — отдельная, необязательная настройка (переменная
    окружения SERPAPI_KEY). Без неё поведение полностью такое же, как и
    раньше: сбой скрейпинга поднимается как обычная ошибка."""
    return bool(os.environ.get("SERPAPI_KEY"))


def _decode_ddg_redirect(href):
    """DuckDuckGo оборачивает ссылки в результатах в свой редирект вида
    "//duckduckgo.com/l/?uddg=<урл-кодированная-настоящая-ссылка>&rut=..."
    — без раскодирования мы бы сохраняли ссылку на сам DuckDuckGo, а не на
    реальный сайт с пиратским контентом."""
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    if "uddg=" in href:
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        values = qs.get("uddg")
        if values:
            return unquote(values[0])
    return href


def _parse_organic_html(html_content):
    """Тот же принцип, что и в yandex_search._parse_organic_html — сначала
    основной разбор по классам DuckDuckGo (result__a / result__snippet,
    подтверждено несколькими независимыми открытыми реализациями), при
    неудаче — запасной вариант через все внешние ссылки."""
    anchors = re.findall(
        r'<a[^>]*class="[^"]*\bresult__a\b[^"]*"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        html_content, re.S,
    )
    snippets = re.findall(
        r'<a[^>]*class="[^"]*\bresult__snippet\b[^"]*"[^>]*>(.*?)</a>',
        html_content, re.S,
    )

    results = []
    for i, (href, raw_title) in enumerate(anchors):
        url = _decode_ddg_redirect(href)
        if not url or "duckduckgo.com" in url:
            continue
        title = re.sub(r"<[^>]*>", "", raw_title).strip()
        description = ""
        if i < len(snippets):
            description = re.sub(r"<[^>]*>", "", snippets[i]).strip()
        results.append({
            "position": len(results) + 1,
            "title": title or "Без заголовка",
            "url": url,
            "description": description,
        })

    if not results:
        # запасной вариант — та же логика, что у yandex_search: если
        # основная разметка не распозналась (сайт мог её поменять), берём
        # все внешние ссылки подряд, не относящиеся к самому DuckDuckGo
        for i, m in enumerate(re.findall(r'href="(https?://[^"]*)"', html_content)):
            if "duckduckgo.com" in m:
                continue
            results.append({"position": i + 1, "title": f"Ссылка {i + 1}", "url": m, "description": ""})

    return results


def _search_one_page_real(query_text, page, session):
    offset = (page - 1) * RESULTS_PER_PAGE
    params = {"q": query_text}
    if offset:
        params["s"] = offset
    resp = session.get(SEARCH_URL, params=params, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise DuckDuckGoSearchError(
            f"DuckDuckGo вернул код {resp.status_code} (страница {page}). "
            f"Частая причина — временная блокировка при слишком частых запросах "
            f"(у DuckDuckGo нет официального API, доступ через обычную HTML-страницу "
            f"результатов, у неё не документированы явные лимиты)."
        )
    return _parse_organic_html(resp.text)


def _search_one_page_via_serpapi(query_text, page, session):
    """Платный резерв — тот же DuckDuckGo, но через SerpApi (engine=duckduckgo),
    легальный оплаченный путь вместо скрейпинга. Формат ответа подтверждён
    по официальной документации: organic_results — список словарей с
    position/title/link/snippet, переводим в тот же внутренний формат
    (position/title/url/description), что и у бесплатного пути."""
    offset = (page - 1) * SERPAPI_RESULTS_PER_PAGE
    params = {
        "engine": "duckduckgo",
        "q": query_text,
        "api_key": os.environ.get("SERPAPI_KEY", ""),
    }
    if offset:
        params["start"] = offset
    resp = session.get(SERPAPI_URL, params=params, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise DuckDuckGoSearchError(f"SerpApi (резерв) вернул код {resp.status_code} (страница {page}).")
    data = resp.json()
    status = (data.get("search_metadata") or {}).get("status")
    if status == "Error":
        raise DuckDuckGoSearchError(f"SerpApi (резерв) вернул ошибку: {data.get('error', 'без подробностей')}")
    results = []
    for item in data.get("organic_results", []):
        results.append({
            "position": item.get("position", len(results) + 1),
            "title": item.get("title") or "Без заголовка",
            "url": item.get("link", ""),
            "description": item.get("snippet", ""),
        })
    return results


def _search_via_serpapi_fallback(query_text, pages, progress_cb, should_stop):
    all_results = []
    session = requests.Session()
    for page in range(1, pages + 1):
        if should_stop and should_stop():
            break
        page_results = _search_one_page_via_serpapi(query_text, page, session)
        all_results.extend(page_results)
        if progress_cb:
            progress_cb(page, pages)
    return all_results


def search(query_text, pages, progress_cb=None, should_stop=None):
    """Тот же интерфейс, что и у yandex_search.search — (query_text, pages,
    progress_cb, should_stop) -> (results, demo_mode). demo_mode здесь
    всегда False (см. is_configured) — сбой самого запроса поднимается
    как настоящая ошибка, если не удалась ни одна страница подряд (и не
    настроен платный резерв, см. модульную документацию выше), ровно как
    и у Yandex."""
    all_results = []
    session = requests.Session()
    last_error = None
    failed_pages = []

    for page in range(1, pages + 1):
        if should_stop and should_stop():
            break
        if page > 1:
            time.sleep(PAGE_DELAY_SEC)
        if should_stop and should_stop():
            break
        try:
            page_results = _search_one_page_real(query_text, page, session)
        except (DuckDuckGoSearchError, requests.RequestException) as e:
            last_error = e
            failed_pages.append(page)
            if progress_cb:
                progress_cb(page, pages)
            continue
        all_results.extend(page_results)
        if progress_cb:
            progress_cb(page, pages)

    if last_error and len(failed_pages) == pages:
        # Бесплатный путь провалился целиком (все страницы подряд) — почти
        # наверняка сработала блокировка. Пробуем платный резерв, если он
        # настроен, вместо того чтобы сразу поднимать ошибку.
        if is_serpapi_fallback_configured():
            try:
                fallback_results = _search_via_serpapi_fallback(query_text, pages, progress_cb, should_stop)
                return fallback_results, False
            except (DuckDuckGoSearchError, requests.RequestException) as fallback_error:
                raise DuckDuckGoSearchError(
                    f"Бесплатный доступ к DuckDuckGo не сработал ({last_error}), "
                    f"платный резерв (SerpApi) тоже не сработал ({fallback_error})."
                )
        raise last_error if isinstance(last_error, DuckDuckGoSearchError) else DuckDuckGoSearchError(str(last_error))

    return all_results, False
