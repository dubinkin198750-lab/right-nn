"""Поиск по VK через официальный API (обновление 23.09).

Два независимых источника, оба по умолчанию выключены:
  • «VK: записи» — метод newsfeed.search (поиск по публичным записям).
    Нужен сервисный ключ приложения VK: переменная VK_SERVICE_TOKEN в .env.
  • «VK: видео» — метод video.search. С сервисным ключом VK его обычно не
    выполняет («нет доступа к методу»), нужен ключ служебного аккаунта
    пользователя: переменная VK_USER_TOKEN в .env.

Известная особенность VK: поиск иногда возвращает пустой результат без
ошибки, а повторный запрос — нормальный. Поэтому пустой ответ повторяется
до двух раз с паузой, и «пусто» не считается доказательством отсутствия
нарушений.
"""
import os
import time

import requests

API_URL = "https://api.vk.com/method/"
API_VERSION = "5.199"
TIMEOUT = 20
PER_PAGE = 100
MAX_PAGES = 3
CALL_DELAY_SEC = 0.4  # лимит VK — несколько запросов в секунду на ключ
EMPTY_RETRIES = 2
EMPTY_RETRY_DELAY_SEC = 1.5


class VkSearchError(RuntimeError):
    pass


def is_configured():
    return bool((os.environ.get("VK_SERVICE_TOKEN") or "").strip())


def is_video_configured():
    return bool((os.environ.get("VK_USER_TOKEN") or "").strip())


def _call(method, params, token):
    try:
        resp = requests.get(API_URL + method, params={**params, "access_token": token, "v": API_VERSION},
                            timeout=TIMEOUT)
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        raise VkSearchError(f"VK не ответил: {type(e).__name__}")
    if "error" in data:
        err = data["error"]
        code = err.get("error_code")
        hints = {5: "неверный или просроченный ключ", 6: "слишком много запросов", 15: "нет доступа к методу",
                 27: "метод недоступен с ключом сообщества/приложения", 29: "исчерпан суточный лимит"}
        raise VkSearchError(f"VK: {hints.get(code, err.get('error_msg', 'ошибка'))} (код {code})")
    return data.get("response") or {}


def _call_with_empty_retry(method, params, token):
    data = {}
    for attempt in range(EMPTY_RETRIES + 1):
        data = _call(method, params, token)
        if data.get("items") or attempt == EMPTY_RETRIES:
            return data
        time.sleep(EMPTY_RETRY_DELAY_SEC)
    return data


def _title_from_text(text, fallback):
    first = (text or "").strip().split("\n", 1)[0].strip()
    return (first[:150] + "…") if len(first) > 150 else (first or fallback)


def search_posts(query_text, pages, progress_cb=None, should_stop=None):
    token = (os.environ.get("VK_SERVICE_TOKEN") or "").strip()
    if not token:
        raise VkSearchError("VK не настроен (нет VK_SERVICE_TOKEN)")
    pages = max(1, min(pages, MAX_PAGES))
    results, start_from = [], None
    for page in range(1, pages + 1):
        if should_stop and should_stop():
            break
        params = {"q": query_text, "count": PER_PAGE}
        if start_from:
            params["start_from"] = start_from
        data = _call_with_empty_retry("newsfeed.search", params, token)
        for it in data.get("items", []):
            owner, pid = it.get("owner_id"), it.get("id")
            if owner is None or pid is None:
                continue
            text = it.get("text") or ""
            results.append({
                "position": len(results) + 1,
                "title": _title_from_text(text, "Запись VK"),
                "url": f"https://vk.com/wall{owner}_{pid}",
                "description": text[:400],
            })
        if progress_cb:
            progress_cb(page, pages)
        start_from = data.get("next_from")
        if not start_from:
            break
        time.sleep(CALL_DELAY_SEC)
    return results, False


def search_videos(query_text, pages, progress_cb=None, should_stop=None):
    token = (os.environ.get("VK_USER_TOKEN") or "").strip()
    if not token:
        raise VkSearchError("Поиск видео VK не настроен (нет VK_USER_TOKEN)")
    pages = max(1, min(pages, MAX_PAGES))
    results = []
    for page in range(1, pages + 1):
        if should_stop and should_stop():
            break
        data = _call_with_empty_retry("video.search", {"q": query_text, "count": PER_PAGE,
                                                       "offset": (page - 1) * PER_PAGE, "adult": 1}, token)
        items = data.get("items", [])
        for it in items:
            owner, vid = it.get("owner_id"), it.get("id")
            if owner is None or vid is None:
                continue
            results.append({
                "position": len(results) + 1,
                "title": it.get("title") or "Видео VK",
                "url": f"https://vk.com/video{owner}_{vid}",
                "description": (it.get("description") or "")[:400],
            })
        if progress_cb:
            progress_cb(page, pages)
        if len(items) < PER_PAGE:
            break
        time.sleep(CALL_DELAY_SEC)
    return results, False
