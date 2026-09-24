"""Прямой поиск по конкретным сайтам из справочника (раздел «Поиск по сайтам»).

В отличие от Яндекс/Google/Avito/Telegram (там поиск идёт через официальные
поисковые API), здесь пользователь сам ведёт список конкретных площадок
(например, форумов и складчин, с которыми уже приходится работать вручную)
и задаёт шаблон поисковой ссылки на каждой из них — приложение просто
подставляет туда фамилию/запрос, скачивает страницу результатов и вытаскивает
из неё ссылки и подписи эвристически (по тегам <a>), без знания конкретной
вёрстки конкретного сайта.

Это не заменяет специализированный парсер под конкретный сайт — на сложных
сайтах (JS-рендеринг, защита от ботов, пагинация) результат может быть
неполным или пустым. Точность формулировки шаблона ссылки и проверка того,
что сайт вообще отдаёт результаты в обычном HTML — ответственность того, кто
ведёт справочник сайтов.
"""
import re
from urllib.parse import quote, urljoin, urlparse

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}
TIMEOUT_SEC = 20
MAX_RESULTS_PER_SITE = 40


class SiteSearchError(RuntimeError):
    pass


class SiteTypeNotSupportedError(SiteSearchError):
    """Сайт отвечает нормально, но не распознан как один из поддерживаемых
    типов (например, не XenForo и нет известного шаблона поиска). Это НЕ
    сбой — просто автопоиск не умеет искать по этому сайту без явного
    шаблона. В отличие от обычной SiteSearchError (таймаут, сеть недоступна),
    такое не должно показываться как «ошибка» в массовом прогоне по
    большому справочнику сайтов, иначе почти все сайты без явного шаблона
    выглядели бы «сломанными», хотя на самом деле просто не подходят под
    автоопределение."""
    pass


def build_search_url(url_template, query):
    if "{query}" not in url_template:
        raise SiteSearchError("В шаблоне ссылки нет плейсхолдера {query} — не знаю, куда подставить запрос")
    return url_template.replace("{query}", quote(query))


def _clean_text(html_fragment):
    text = re.sub(r"<[^>]+>", " ", html_fragment)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_links(html, base_url):
    """Эвристика: берём все <a href=...>текст</a>, приводим ссылки к абсолютным,
    фильтруем служебные (javascript:, #, mailto:, картинки/стили) и дубли."""
    base_domain = urlparse(base_url).netloc
    results = []
    seen = set()

    for m in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href, inner = m.group(1), m.group(2)
        if href.startswith(("javascript:", "#", "mailto:", "tel:")):
            continue
        text = _clean_text(inner)
        if not text or len(text) < 3:
            continue
        abs_url = urljoin(base_url, href)
        parsed = urlparse(abs_url)
        if parsed.scheme not in ("http", "https"):
            continue
        if abs_url in seen:
            continue
        seen.add(abs_url)
        results.append({"title": text[:200], "url": abs_url, "description": "", "_same_domain": parsed.netloc == base_domain})
        if len(results) >= MAX_RESULTS_PER_SITE * 3:  # запас, отфильтруем ниже
            break

    # приоритет ссылкам на том же домене (обычно это и есть найденные материалы,
    # а не переходы на внешнюю рекламу/партнёров)
    same_domain = [r for r in results if r["_same_domain"]]
    other = [r for r in results if not r["_same_domain"]]
    ordered = same_domain + other
    for r in ordered:
        r.pop("_same_domain", None)
    return ordered[:MAX_RESULTS_PER_SITE]


STOP_WORDS = {"и", "в", "на", "по", "за", "от", "для", "или", "не", "как", "the", "and", "or", "of", "to"}


def _query_words(query, min_len=3):
    words = re.findall(r"\w+", query.lower(), re.UNICODE)
    return [w for w in words if len(w) >= min_len and w not in STOP_WORDS]


def filter_by_relevance(results, query):
    """Оставляет только ссылки, в заголовке которых встречается хотя бы одно
    значимое слово из запроса. Если сайт на самом деле не выполнил поиск (а
    просто вернул обычную страницу — например, потому что его поиск требует
    сессию/JS и не работает через простую GET-ссылку), в выдаче окажется общая
    навигация сайта («Вход», «Регистрация», «Форумы» и т.п.) — эта проверка
    её отсекает: раз в заголовке нет ни слова из запроса, скорее всего, это
    не результат поиска."""
    words = _query_words(query)
    if not words:
        return results
    kept = []
    for r in results:
        haystack = r["title"].lower()
        if any(w in haystack for w in words):
            kept.append(r)
    return kept


def _configured_domain(site):
    host = urlparse(site["url_template"]).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _detect_domain_redirect(site, results):
    """Если реально полученные ссылки указывают на другой домен, чем настроен
    в справочнике сайтов — сайт, скорее всего, целиком переехал (частое
    явление у пиратских форумов). Возвращает новый домен или None."""
    if not results:
        return None
    configured = _configured_domain(site)
    result_domains = set()
    for r in results:
        host = urlparse(r["url"]).netloc.lower()
        result_domains.add(host[4:] if host.startswith("www.") else host)
    if len(result_domains) == 1:
        (only_domain,) = result_domains
        if only_domain and only_domain != configured:
            return only_domain
    return None


# Режимы сайта (поле «mode», обновление 23.09). Если поле не задано —
# сайт работает ровно как раньше (по полю type: auto/generic/xenforo).
SITE_MODES = {
    "auto": "автоматически (шаблон, при неудаче — XenForo)",
    "template": "только по шаблону поиска",
    "xenforo": "форум XenForo",
    "yandex": "через Яндекс (site:домен)",
    "manual": "ручная проверка (не ищется автоматически)",
    "off": "отключён",
}
SKIPPED_MODES = {"manual", "off"}


def site_mode(site):
    mode = site.get("mode")
    if mode in SITE_MODES:
        return mode
    return "xenforo" if site.get("type") == "xenforo" else "auto"


def _search_via_yandex(site, query):
    from . import yandex_search
    if not yandex_search.is_configured():
        raise SiteSearchError("Режим «через Яндекс» недоступен: Яндекс не настроен")
    domain = _configured_domain(site)
    if not domain:
        raise SiteSearchError("Не удалось определить домен сайта для поиска через Яндекс")
    try:
        items, _demo = yandex_search.search(f"{query} site:{domain}", 1)
    except Exception as e:  # noqa
        raise SiteSearchError(f"Поиск через Яндекс не удался: {e}")
    results = []
    for it in items:
        results.append({"title": it.get("title", ""), "url": it.get("url", ""),
                        "description": it.get("description", ""), "source": site["name"], "position": None})
    return [r for r in results if r["url"]]


def search_one_site(site, query):
    mode = site_mode(site)
    if mode == "yandex":
        return _search_via_yandex(site, query)
    if mode == "template":
        results = search_generic(site, query)
    elif mode == "xenforo":
        results = search_xenforo(site, query)
    else:
        # "auto" и "generic" (в т.ч. сайты, сохранённые до появления авто-режима)
        # обрабатываются одинаково — сначала обычная ссылка, при неудаче —
        # автоматическая попытка через цепочку XenForo.
        results = search_auto(site, query)

    new_domain = _detect_domain_redirect(site, results)
    if new_domain:
        for r in results:
            r["site_redirected_to"] = new_domain
    return results


def classify_error(message):
    """Статус по тексту ошибки: защита от ботов / недоступен / прочая ошибка."""
    m = (message or "").lower()
    if any(x in m for x in ("403", "503", "429", "cloudflare", "ddos", "captcha", "forbidden")):
        return "blocked"
    if any(x in m for x in ("не ответил", "timeout", "timed out", "connection", "name or service",
                            "resolve", "refused", "unreachable", "ssl")):
        return "unavailable"
    return "error"


STATUS_LABELS = {
    "ok": "работает",
    "empty": "работает, ничего не найдено",
    "no_template": "шаблон поиска не задан",
    "blocked": "защита от ботов / доступ запрещён",
    "unavailable": "сайт недоступен",
    "error": "ошибка поиска",
    "skipped": "не ищется (ручная проверка или отключён)",
}


def _base_origin(url_or_template):
    parsed = urlparse(url_or_template)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


# Диагностика для итогов прогона (шаблон не задан и т.п.) передаётся через
# локальное хранилище потока, а не параметром, — чтобы не менять порядок
# вызова search_one_site(site, query), на который опираются другие части.
import threading as _threading
_diag_local = _threading.local()


def _diag():
    return getattr(_diag_local, "data", None)


def search_auto(site, query, diag=None):
    """Режим по умолчанию: сначала пробуем обычную GET-ссылку по шаблону.
    Если она не дала ни одного релевантного результата (или в шаблоне вообще
    нет {query} — то есть указан просто адрес сайта), пробуем цепочку
    XenForo (токен → POST → редирект) на этом же домене. Так не нужно вручную
    выбирать тип сайта — работает «из коробки» для обоих вариантов.

    Важно: если обе попытки закончились именно ОШИБКОЙ (сайт недоступен,
    таймаут и т.п.) — это должно быть видно как ошибка, а не молча
    выглядеть как «ничего не нашли». Иначе на большом справочнике сайтов
    не отличить настоящие «пусто» от того, что до сайта вообще не достучались."""
    generic_error = None
    generic_results = []
    if "{query}" in site["url_template"]:
        try:
            generic_results = search_generic(site, query)
        except SiteSearchError as e:
            generic_error = e

    if generic_results:
        return generic_results

    base = _base_origin(site["url_template"])
    xenforo_error = None
    if base:
        try:
            xf_results = search_xenforo({"name": site["name"], "url_template": base}, query)
            if xf_results:
                return xf_results
        except SiteTypeNotSupportedError:
            # не XenForo — это нормально, не ошибка, просто нечем автоматически искать
            d = diag if diag is not None else _diag()
            if d is not None and "{query}" not in site["url_template"]:
                d["no_template"] = True
        except SiteSearchError as e:
            xenforo_error = e

    # до этой точки дошли, только если ни один способ не дал результатов.
    # Если хотя бы одна из попыток была реальной ошибкой (не просто "пусто"
    # и не просто "не тот тип сайта"), это стоит показать, а не проглатывать молча.
    if generic_error and xenforo_error:
        raise SiteSearchError(f"{generic_error} Также не удалось через XenForo-цепочку: {xenforo_error}")
    if generic_error:
        raise generic_error
    if xenforo_error:
        raise xenforo_error
    return []


def search_generic(site, query):
    url = build_search_url(site["url_template"], query)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SEC)
        resp.raise_for_status()
    except requests.Timeout:
        raise SiteSearchError(
            f"Сайт не ответил за {TIMEOUT_SEC} секунд ({url}). "
            f"Возможно, сайт медленный, временно недоступен, или блокирует автоматические запросы."
        )
    except requests.RequestException as e:
        raise SiteSearchError(f"Не удалось загрузить {url}: {e}")

    # resp.url — адрес ПОСЛЕ всех редиректов (requests идёт по ним сам,
    # allow_redirects=True по умолчанию для GET). Важно разрешать
    # относительные ссылки именно от него, а не от исходного url: если
    # сайт целиком переехал на другой домен, страница физически пришла
    # оттуда, и ссылки на ней относительные к новому домену, не к старому.
    links = extract_links(resp.text, resp.url)
    relevant = filter_by_relevance(links, query)
    for r in relevant:
        r["source"] = site["name"]
        r["position"] = None
    return relevant


XENFORO_TOKEN_RE = re.compile(r'name="_xfToken"\s+value="([^"]+)"', re.I)


def search_xenforo(site, query):
    """Форумы на движке XenForo (видно по адресам вида /threads/..., /members/...,
    /forums/...) обычно не отдают результаты поиска по простой GET-ссылке —
    поиск выполняется через POST-запрос с CSRF-токеном, а сервер в ответ
    генерирует отдельный числовой ID результата и делает редирект на страницу
    с реальными ссылками (тот самый `.../search/18654/?q=...`).

    Здесь эта цепочка имитируется вручную:
      1. GET форумной страницы поиска — достаём оттуда токен _xfToken.
      2. POST на /search/search с этим токеном и поисковым запросом.
      3. requests сам идёт по редиректу (по умолчанию allow_redirects=True) —
         в ответе оказывается страница уже с реальными результатами.

    Это лучшая попытка по общей схеме XenForo 2.x — конкретные форумы могут
    отличаться версией/настройками и не сработать «из коробки»."""
    base = site["url_template"].rstrip("/")
    search_form_url = f"{base}/search/"
    search_post_url = f"{base}/search/search"

    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        form_resp = session.get(search_form_url, timeout=TIMEOUT_SEC)
        form_resp.raise_for_status()
    except requests.Timeout:
        raise SiteSearchError(f"Сайт не ответил за {TIMEOUT_SEC} секунд при открытии формы поиска ({search_form_url}).")
    except requests.RequestException as e:
        raise SiteSearchError(f"Не удалось открыть форму поиска {search_form_url}: {e}")

    # если начальная страница поиска сама была с редиректом (например, весь
    # форум переехал на новый домен) — строим адрес для POST от РЕАЛЬНОГО
    # адреса после редиректа, а не от исходного base. Иначе POST ушёл бы на
    # старый домен, где формы поиска может уже не быть вовсе.
    actual_base = f"{urlparse(form_resp.url).scheme}://{urlparse(form_resp.url).netloc}"
    if actual_base != base:
        search_post_url = f"{actual_base}/search/search"

    token_match = XENFORO_TOKEN_RE.search(form_resp.text)
    if not token_match:
        raise SiteTypeNotSupportedError(
            f"Не нашёл CSRF-токен (_xfToken) на странице {search_form_url} — "
            f"возможно, это не XenForo-форум, или у него нестандартная форма поиска."
        )
    token = token_match.group(1)

    try:
        result_resp = session.post(
            search_post_url,
            data={"keywords": query, "order": "date", "_xfToken": token},
            timeout=TIMEOUT_SEC,
        )
        result_resp.raise_for_status()
    except requests.Timeout:
        raise SiteSearchError(f"Сайт не ответил за {TIMEOUT_SEC} секунд при выполнении поиска ({search_post_url}).")
    except requests.RequestException as e:
        raise SiteSearchError(f"Не удалось выполнить поиск на {search_post_url}: {e}")

    links = extract_links(result_resp.text, result_resp.url)
    relevant = filter_by_relevance(links, query)
    for r in relevant:
        r["source"] = site["name"]
        r["position"] = None
    return relevant


def search_sites(sites, queries, progress_cb=None, should_stop=None, report=None):
    """Ищет по каждому сайту из списка все переданные запросы по очереди
    (queries — список; одна строка тоже допускается для удобства). Ошибка на
    одном сайте/запросе не останавливает остальные.

    Результаты дедуплицируются по ссылке (одна и та же раздача часто
    находится по нескольким формулировкам запроса) — каждый результат при
    этом помечается полем "matched_query", каким именно запросом он нашёлся
    (первым из подошедших). Ошибки по сайту не повторяются для каждого
    запроса отдельно — обычно это сбой соединения/доступа, не зависящий от
    текста запроса, и показывать его несколько раз подряд не полезно.

    should_stop — необязательный колбэк без аргументов: если возвращает
    True, поиск останавливается досрочно и возвращает то, что успело
    накопиться до этого момента.

    report — необязательный словарь site_id -> {"status", "found", "detail"}:
    итог по каждому сайту (работает / шаблон не задан / защита / недоступен /
    ошибка / не ищется). Сайты в режимах «ручная проверка» и «отключён» не
    опрашиваются вовсе.

    Возвращает (results, errors, redirects) — redirects: по одному
    уведомлению на сайт, если он целиком переехал на другой домен, не по
    одному на каждую найденную ссылку/запрос."""
    if isinstance(queries, str):
        queries = [queries]
    queries = [q.strip() for q in queries if q and q.strip()]
    if not queries:
        queries = [""]

    all_results = []
    seen_urls = set()
    errors = []
    errored_site_ids = set()
    redirects = []
    redirected_site_ids = set()

    total = len(sites) * len(queries)
    idx = 0
    # порядок обхода намеренно "запрос снаружи, сайт внутри" — а не наоборот.
    # Если несколько вариантов запроса, повторные обращения к ОДНОМУ и тому
    # же сайту (по каждому следующему запросу) должны быть разнесены во
    # времени, а не идти подряд одно за другим — иначе именно это может
    # вызвать блокировку по IP на стороне самого сайта (у многих форумов
    # есть простая защита от частых запросов). При таком порядке между двумя
    # обращениями к одному сайту всегда проходит время на все остальные сайты
    # из справочника — это уже достаточный интервал сам по себе.
    def rep(site):
        if report is None:
            return None
        return report.setdefault(site["id"], {"name": site["name"], "status": None, "found": 0, "detail": ""})

    for site in sites:
        if site_mode(site) in SKIPPED_MODES and report is not None:
            r = rep(site)
            r["status"] = "skipped"
    active_sites = [s for s in sites if site_mode(s) not in SKIPPED_MODES]
    total = len(active_sites) * len(queries)

    for query in queries:
        for site in active_sites:
            if should_stop and should_stop():
                return all_results, errors, redirects
            if progress_cb:
                label = site["name"] if len(queries) == 1 else f"{site['name']} — «{query}»"
                progress_cb(idx, total, label)
            idx += 1
            diag = {}
            _diag_local.data = diag
            r = rep(site)
            try:
                site_results = search_one_site(site, query)
            except SiteSearchError as e:
                _diag_local.data = None
                if site["id"] not in errored_site_ids:
                    errored_site_ids.add(site["id"])
                    errors.append({"site": site["name"], "error": str(e)})
                if r is not None and r["status"] in (None, "no_template", "empty"):
                    r["status"] = classify_error(str(e))
                    r["detail"] = str(e)[:300]
                continue
            _diag_local.data = None
            if r is not None:
                if diag.get("no_template") and not site_results:
                    if r["status"] is None:
                        r["status"] = "no_template"
                elif r["status"] in (None, "no_template", "empty"):
                    r["status"] = "ok" if site_results else "empty"

            if site_results and site_results[0].get("site_redirected_to") and site["id"] not in redirected_site_ids:
                redirected_site_ids.add(site["id"])
                redirects.append({
                    "site": site["name"],
                    "site_id": site["id"],
                    "old_domain": _configured_domain(site),
                    "new_domain": site_results[0]["site_redirected_to"],
                })

            for res in site_results:
                if res["url"] in seen_urls:
                    continue
                seen_urls.add(res["url"])
                res["matched_query"] = query
                all_results.append(res)
                if r is not None:
                    r["found"] += 1

    return all_results, errors, redirects
