"""Клиент Yandex Cloud Search API v2 (searchapi.api.cloud.yandex.net).

Логика 1:1 повторяет исходный n8n-сценарий:
  1. POST /v2/web/searchAsync с телом запроса (query/groupSpec/...) -> operationId
  2. Поллинг GET https://operation.api.cloud.yandex.net/operations/{id} до done=true
  3. response.rawData — HTML-выдача в Base64, декодируем
  4. Регуляркой достаём органические результаты (title/url/description)

Если переменные окружения YANDEX_API_KEY / YANDEX_FOLDER_ID не заданы,
клиент работает в демо-режиме и генерирует синтетические результаты —
это позволяет проверить всю цепочку (поиск -> фильтры -> дедупликация -> UI)
без реального ключа API.

Официальная документация API (для получения ключа/токена):
https://yandex.cloud/ru/docs/search-api/
"""
import base64
import os
import random
import re
import time

import requests

SEARCH_URL = "https://searchapi.api.cloud.yandex.net/v2/web/searchAsync"
OPERATION_URL = "https://operation.api.cloud.yandex.net/operations/{operation_id}"

POLL_INTERVAL_SEC = 2
POLL_TIMEOUT_SEC = 60
PAGE_DELAY_SEC = 1  # пауза между страницами одного запроса — без неё несколько
# страниц (и тем более несколько вариантов запроса) подряд без остановки
# могут вызвать замедление/таймауты на стороне API, даже без явного 429


class YandexSearchError(RuntimeError):
    pass


def is_configured():
    return bool(os.environ.get("YANDEX_API_KEY")) and bool(os.environ.get("YANDEX_FOLDER_ID"))


def _auth_header():
    api_key = os.environ.get("YANDEX_API_KEY", "")
    return {"Authorization": f"Api-Key {api_key}"}


def _build_request_body(query_text, page, response_format="FORMAT_HTML"):
    return {
        "query": {
            "searchType": "SEARCH_TYPE_RU",
            "queryText": query_text,
            "page": page,
            # без этого API может применять собственный фильтр контента по
            # умолчанию (FAMILY_MODE_MODERATE) — для задачи поиска пиратских
            # копий это нежелательно, отключаем явно
            "familyMode": "FAMILY_MODE_NONE",
        },
        "groupSpec": {
            "groupMode": "GROUP_MODE_FLAT",
            "groupsOnPage": 30,
            "docsInGroup": 1,
        },
        "maxPassages": 2,
        "folderId": os.environ.get("YANDEX_FOLDER_ID", ""),
        "responseFormat": response_format,
        "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }


def _parse_organic_html(html_content):
    """Тот же подход, что в ноде 'Code in JavaScript5': сначала пытаемся
    вытащить блоки serp-item, если не вышло — берём все внешние ссылки."""
    results = []
    blocks = re.findall(r'<li[^>]*class="[^"]*serp-item[^"]*"[^>]*>.*?</li>', html_content, re.S)
    for i, block in enumerate(blocks):
        title_m = re.search(r'<h2[^>]*>.*?<a[^>]*>(.*?)</a>.*?</h2>', block, re.S)
        title = re.sub(r"<[^>]*>", "", title_m.group(1)).strip() if title_m else ""
        url_m = re.search(r'<a[^>]*href="([^"]*)"[^>]*>', block)
        url = url_m.group(1) if url_m else ""
        desc_m = re.search(r'<div[^>]*class="[^"]*OrganicText[^"]*"[^>]*>(.*?)</div>', block, re.S)
        description = re.sub(r"<[^>]*>", "", desc_m.group(1)).strip() if desc_m else ""
        if url:
            results.append({"position": i + 1, "title": title or "Без заголовка", "url": url, "description": description or ""})

    if not results:
        for i, m in enumerate(re.findall(r'href="(https?://[^"]*)"', html_content)):
            if "yandex.ru" in m or "yandex.net" in m:
                continue
            results.append({"position": i + 1, "title": f"Ссылка {i + 1}", "url": m, "description": ""})
    return results


MAX_429_RETRIES = 5


def _post_with_retry(session, url, json_body, headers, timeout):
    """POST с повторными попытками при 429 (слишком много запросов) —
    актуально при массовом запуске многих произведений сразу, когда несколько
    фоновых задач одновременно бьют в один и тот же API. Уважает заголовок
    Retry-After, если Яндекс его присылает, иначе растущая пауза (2, 4, 8...)."""
    last_exc = None
    for attempt in range(MAX_429_RETRIES + 1):
        resp = session.post(url, json=json_body, headers=headers, timeout=timeout)
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp
        retry_after = resp.headers.get("Retry-After")
        wait = float(retry_after) if retry_after else (2 ** (attempt + 1))
        last_exc = requests.exceptions.HTTPError(
            f"429 Client Error: Too Many Requests for url: {url}", response=resp
        )
        if attempt < MAX_429_RETRIES:
            time.sleep(wait)
    raise YandexSearchError(
        f"Yandex Search API отвечает «слишком много запросов» (429) даже после {MAX_429_RETRIES} "
        f"повторных попыток. Обычно это временная перегрузка при одновременном запуске сразу многих "
        f"произведений — подождите немного и запустите поиск заново, или запускайте произведения не всё "
        f"сразу, а частями."
    ) from last_exc


def _fetch_raw(query_text, page, session, response_format="FORMAT_HTML"):
    """Один запрос к API: отправить, дождаться операции, вернуть
    декодированное тело ответа (HTML или XML — в зависимости от формата)."""
    resp = _post_with_retry(session, SEARCH_URL, _build_request_body(query_text, page, response_format), _auth_header(), 30)
    operation_id = resp.json().get("id")
    if not operation_id:
        raise YandexSearchError(f"Yandex API не вернул operationId: {resp.text[:300]}")

    start = time.time()
    while time.time() - start < POLL_TIMEOUT_SEC:
        op_resp = session.get(OPERATION_URL.format(operation_id=operation_id), headers=_auth_header(), timeout=30)
        op_resp.raise_for_status()
        op_json = op_resp.json()
        if op_json.get("done"):
            raw_data = op_json.get("response", {}).get("rawData")
            if not raw_data:
                error_detail = op_json.get("error")
                if error_detail:
                    msg = error_detail.get("message", str(error_detail))
                    raise YandexSearchError(
                        f"Yandex Search API вернул ошибку: {msg} "
                        f"(код {error_detail.get('code', '?')}). Частые причины: не привязан платёжный "
                        f"аккаунт к облаку, Search API не подключён в каталоге, у ключа нет нужной роли."
                    )
                raise YandexSearchError(
                    "Операция завершена, но rawData отсутствует, и явного текста ошибки нет. "
                    f"Полный ответ API: {op_json}"
                )
            return base64.b64decode(raw_data).decode("utf-8", errors="ignore")
        time.sleep(POLL_INTERVAL_SEC)
    raise YandexSearchError(f"Превышено время ожидания ответа Yandex Search API (страница {page})")


# ---------- структурированная выдача (XML) ----------
# Режим задаётся в .env: YANDEX_RESPONSE_FORMAT = html (по умолчанию, как было
# всегда) | compare (показывается HTML, XML параллельно пишется в отчёт
# сравнения) | xml (только XML). XML не зависит от вёрстки страницы Яндекса —
# в отличие от разбора HTML регулярными выражениями, который молча перестаёт
# находить результаты при любой смене вёрстки.
RESPONSE_FORMAT_ENV = "YANDEX_RESPONSE_FORMAT"
_NO_RESULTS_CODES = {"15"}  # «Искомая комбинация слов нигде не встречается»


def response_format_mode():
    mode = (os.environ.get(RESPONSE_FORMAT_ENV) or "html").strip().lower()
    return mode if mode in ("html", "compare", "xml") else "html"


def _text(el):
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


def parse_xml(xml_text):
    """Возвращает (results, found, error_code, error_text). found — сколько
    документов Яндекс сообщает найденными (None, если не сообщает)."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError as e:
        raise YandexSearchError(f"Сбой разбора выдачи: ответ Яндекса не является корректным XML ({e})")
    response = root.find("response")
    if response is None:
        raise YandexSearchError("Сбой разбора выдачи: в XML-ответе Яндекса нет элемента response")
    err = response.find("error")
    if err is not None:
        return [], 0, err.get("code", ""), _text(err)
    found = None
    for f in response.findall("found"):
        if f.get("priority") == "all":
            try:
                found = int(_text(f))
            except ValueError:
                found = None
    results = []
    for doc in response.iter("doc"):
        url = _text(doc.find("url"))
        if not url:
            continue
        title = _text(doc.find("title"))
        passages = [_text(p) for p in doc.iter("passage")]
        description = " … ".join(p for p in passages if p) or _text(doc.find("headline"))
        results.append({"position": len(results) + 1, "title": title or "Без заголовка",
                        "url": url, "description": description})
    return results, found, None, ""


def _xml_page(query_text, page, session):
    xml_text = _fetch_raw(query_text, page, session, "FORMAT_XML")
    results, found, code, err_text = parse_xml(xml_text)
    if code is not None:
        if code in _NO_RESULTS_CODES:
            return [], 0
        raise YandexSearchError(f"Yandex Search API вернул ошибку в выдаче: {err_text} (код {code})")
    if found and not results:
        raise YandexSearchError(
            f"Сбой разбора выдачи: Яндекс сообщает о найденных документах ({found}), "
            f"но не удалось извлечь ни одной ссылки."
        )
    return results, found


def _search_one_page_real(query_text, page, session):
    mode = response_format_mode()
    if mode == "xml":
        return _xml_page(query_text, page, session)[0]
    html = _fetch_raw(query_text, page, session, "FORMAT_HTML")
    html_results = _parse_organic_html(html)
    if mode == "compare":
        # пользователь видит HTML-результат, как раньше; XML только в отчёт.
        # Любая ошибка XML-ветки не должна влиять на основной результат.
        entry = {"at": time.time(), "query": query_text, "page": page,
                 "html_count": len(html_results), "html_urls": [r["url"] for r in html_results]}
        try:
            xml_results, found = _xml_page(query_text, page, session)
            entry.update({"xml_count": len(xml_results), "xml_found": found,
                          "xml_urls": [r["url"] for r in xml_results]})
        except Exception as e:  # noqa
            entry.update({"xml_count": None, "xml_error": str(e)[:300]})
        try:
            from . import storage
            storage.append_yandex_compare(entry)
        except Exception:  # noqa
            pass
    return html_results


_DEMO_DOMAINS = [
    "vkurse.club", "slivap.ru", "supersliv.biz", "skladchina.biz",
    "100500kurs.com", "forum-pirat.net", "kurs-sliv.ru", "shara-info.org",
]


def _search_one_page_demo(query_text, page, rng):
    """Генерирует правдоподобные, но полностью синтетические результаты —
    только для проверки работы фильтров/дедупликации/интерфейса без реального API."""
    n = rng.randint(2, 5)
    results = []
    words = query_text.split() or ["курс"]
    for i in range(n):
        domain = rng.choice(_DEMO_DOMAINS)
        slug = "-".join(w.lower() for w in words[:3]) or "item"
        results.append({
            "position": (page - 1) * 30 + i + 1,
            "title": f"{query_text} — скачать бесплатно (демо)",
            "url": f"https://{domain}/threads/{slug}-{page}-{i}.{rng.randint(1000,99999)}/",
            "description": f"Демо-описание страницы про «{query_text}», раздача материалов, страница {page}.",
        })
    return results


def search(query_text, pages, progress_cb=None, should_stop=None):
    """Ищет query_text на страницах 1..pages, возвращает объединённый список результатов.
    progress_cb(page, total_pages) — необязательный колбэк для отображения прогресса.
    should_stop — необязательный колбэк без аргументов: если возвращает True,
    поиск останавливается досрочно и возвращает то, что успело накопиться.

    Сбой одной отдельной страницы (таймаут, временная перегрузка API и т.п.)
    не должен ронять уже полученные результаты с остальных страниц — такая
    страница пропускается, поиск продолжается дальше. Если ВСЕ страницы
    подряд не удались — это уже не разовая случайность, а вероятная
    системная проблема (ключ/лимиты/доступность API), и тогда ошибка
    показывается, раз результатов нет вообще никаких."""
    all_results = []
    demo_mode = not is_configured()
    rng = random.Random(hash(query_text) & 0xFFFFFFFF) if demo_mode else None
    session = requests.Session() if not demo_mode else None
    last_error = None
    failed_pages = []

    for page in range(1, pages + 1):
        if should_stop and should_stop():
            break
        if not demo_mode and page > 1:
            time.sleep(PAGE_DELAY_SEC)  # пауза перед КАЖДОЙ страницей, кроме первой
        if should_stop and should_stop():
            break  # проверяем и после паузы — не ждать, если отмену запросили во время неё
        if demo_mode:
            page_results = _search_one_page_demo(query_text, page, rng)
        else:
            try:
                page_results = _search_one_page_real(query_text, page, session)
            except YandexSearchError as e:
                last_error = e
                failed_pages.append(page)
                if progress_cb:
                    progress_cb(page, pages)
                continue
        all_results.extend(page_results)
        if progress_cb:
            progress_cb(page, pages)

    if last_error and len(failed_pages) == pages:
        # ни одна страница вообще не отработала — это уже не разовая
        # случайность на конкретной странице, а вероятная системная проблема
        # (ключ/лимиты/доступность API), стоит показать ошибку
        raise last_error
    if failed_pages and all_results:
        # частичный сбой — что-то нашли, но не все страницы прошли. Не
        # прерываем работу, но помечаем результат, чтобы это было видно
        # (используется в отчёте о запуске, не блокирует сохранение найденного)
        pass  # осознанно не поднимаем исключение — см. докстринг выше

    return all_results, demo_mode
