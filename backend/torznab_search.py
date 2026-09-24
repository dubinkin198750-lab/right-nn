"""Поиск по торрент-трекерам через агрегатор с интерфейсом Torznab
(Jackett или Prowlarr, устанавливается на сервере отдельно).

Приложение обращается к ОДНОМУ адресу агрегатора, а тот уже опрашивает
настроенные в нём трекеры. Большинство трекеров заблокированы в России,
поэтому доступ к ним (прокси/обход) настраивается в самом агрегаторе, а не
здесь. Берутся только название раздачи, страница раздачи на трекере и
дата — файлы и .torrent не скачиваются.

Настройки в .env (по умолчанию источник выключен):
  TORZNAB_URL      — полный адрес до /api, например для Jackett:
                     http://127.0.0.1:9117/api/v2.0/indexers/all/results/torznab/api
  TORZNAB_API_KEY  — ключ API агрегатора
"""
import os
import xml.etree.ElementTree as ET

import requests

TIMEOUT = 90  # агрегатор сам ждёт ответа всех трекеров — это небыстро


class TorznabSearchError(RuntimeError):
    pass


def is_configured():
    return bool((os.environ.get("TORZNAB_URL") or "").strip())


def _child_text(item, tag):
    el = item.find(tag)
    return (el.text or "").strip() if el is not None and el.text else ""


def parse(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise TorznabSearchError(f"Агрегатор вернул некорректный ответ ({e})")
    if root.tag == "error":
        raise TorznabSearchError(f"Агрегатор: {root.get('description', 'ошибка')} (код {root.get('code', '?')})")
    results = []
    for item in root.iter("item"):
        page = _child_text(item, "comments")
        guid = _child_text(item, "guid")
        url = page or (guid if guid.startswith("http") else "")
        if not url or url.startswith("magnet:"):
            continue
        indexer = _child_text(item, "jackettindexer") or _child_text(item, "prowlarrindexer")
        date = _child_text(item, "pubDate")
        results.append({
            "position": len(results) + 1,
            "title": _child_text(item, "title") or "Раздача",
            "url": url,
            "description": ", ".join(p for p in (indexer, date) if p),
        })
    return results


def search(query_text, pages, progress_cb=None, should_stop=None):
    url = (os.environ.get("TORZNAB_URL") or "").strip()
    if not url:
        raise TorznabSearchError("Торрент-агрегатор не настроен (нет TORZNAB_URL)")
    if should_stop and should_stop():
        return [], False
    params = {"t": "search", "q": query_text}
    key = (os.environ.get("TORZNAB_API_KEY") or "").strip()
    if key:
        params["apikey"] = key
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise TorznabSearchError(f"Агрегатор недоступен: {type(e).__name__}")
    if resp.status_code != 200:
        raise TorznabSearchError(f"Агрегатор ответил кодом {resp.status_code}")
    results = parse(resp.text)
    if progress_cb:
        progress_cb(1, 1)
    return results, False
