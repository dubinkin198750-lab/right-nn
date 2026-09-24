"""Клиент Google Custom Search JSON API.

Требует создать Programmable Search Engine (настроенный на поиск по всему
интернету) и получить API-ключ:
https://developers.google.com/custom-search/v1/introduction

Переменные окружения: GOOGLE_API_KEY, GOOGLE_CSE_ID.
Без них — демо-режим с синтетическими результатами, как и у Yandex-клиента.

API отдаёт максимум 10 результатов за один запрос и до 100 суммарно
(постранично через параметр start) — это ограничение самого Google, не наше.
"""
import os
import random

import requests

SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
RESULTS_PER_PAGE = 10
MAX_PAGES = 10  # Google API отдаёт не больше 100 результатов (10 страниц по 10)


def is_configured():
    return bool(os.environ.get("GOOGLE_API_KEY")) and bool(os.environ.get("GOOGLE_CSE_ID"))


def _search_one_page_real(query_text, page, session):
    start = (page - 1) * RESULTS_PER_PAGE + 1
    params = {
        "key": os.environ.get("GOOGLE_API_KEY", ""),
        "cx": os.environ.get("GOOGLE_CSE_ID", ""),
        "q": query_text,
        "start": start,
        "num": RESULTS_PER_PAGE,
    }
    resp = session.get(SEARCH_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items", [])
    results = []
    for i, it in enumerate(items):
        results.append({
            "position": start + i,
            "title": it.get("title", "Без заголовка"),
            "url": it.get("link", ""),
            "description": it.get("snippet", "") or "",
        })
    return results


_DEMO_DOMAINS = [
    "vkurse.club", "slivap.ru", "supersliv.biz", "skladchina.biz",
    "100500kurs.com", "forum-pirat.net", "kurs-sliv.ru", "shara-info.org",
]


def _search_one_page_demo(query_text, page, rng):
    n = rng.randint(1, 4)
    results = []
    words = query_text.split() or ["курс"]
    for i in range(n):
        domain = rng.choice(_DEMO_DOMAINS)
        slug = "-".join(w.lower() for w in words[:3]) or "item"
        results.append({
            "position": (page - 1) * RESULTS_PER_PAGE + i + 1,
            "title": f"{query_text} — скачать бесплатно (демо, Google)",
            "url": f"https://{domain}/g-threads/{slug}-{page}-{i}.{rng.randint(1000,99999)}/",
            "description": f"Демо-описание (Google) страницы про «{query_text}», страница {page}.",
        })
    return results


def search(query_text, pages, progress_cb=None, should_stop=None):
    """should_stop — необязательный колбэк без аргументов: если возвращает
    True, поиск останавливается досрочно (после текущей страницы) и
    возвращает то, что успело накопиться, вместо того чтобы падать с ошибкой
    или тихо игнорировать запрос на отмену."""
    pages = min(pages, MAX_PAGES)
    all_results = []
    demo_mode = not is_configured()
    rng = random.Random(hash(query_text) & 0xFFFFFFFF) if demo_mode else None
    session = requests.Session() if not demo_mode else None

    for page in range(1, pages + 1):
        if should_stop and should_stop():
            break
        if demo_mode:
            page_results = _search_one_page_demo(query_text, page, rng)
        else:
            page_results = _search_one_page_real(query_text, page, session)
        all_results.extend(page_results)
        if progress_cb:
            progress_cb(page, pages)
        if not demo_mode and len(page_results) < RESULTS_PER_PAGE:
            break  # результаты закончились раньше лимита страниц

    return all_results, demo_mode
