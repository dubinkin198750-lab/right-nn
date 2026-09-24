"""Фильтрация и дедупликация результатов — логика 1:1 портирована
из нод "КОД ДЛЯ ИСКЛЮЧЕНИЯ ОФИЦИАЛОВ", "Фильтр описания/url по ключевым словам"
и "Убираем дубли" исходного n8n-сценария.
"""


def exclude_blocked_domains(items, blocked_domains):
    """Убирает результаты, чей URL содержит один из официальных/разрешённых доменов."""
    blocked = [d.lower() for d in blocked_domains]
    kept = []
    for item in items:
        url = (item.get("url") or "").lower()
        if any(domain in url for domain in blocked):
            continue
        kept.append(item)
    return kept


def filter_by_keywords(items, keywords, negative_keywords=None):
    """Оставляет результат, если совпало хотя бы одно правило (ИЛИ между строками)
    из положительных ключевых слов И при этом ни одно стоп-слово не найдено (исключение).

    Правило (одна строка положительных слов) бывает двух видов:
      - "grammar mama"           -> точная фраза: подстрока должна встретиться как есть
      - "grammar, mama"          -> набор слов (через запятую): все слова должны
                                     встретиться в тексте, но не обязательно рядом
                                     и не обязательно в этом порядке (И между словами)

    Стоп-слова (negative_keywords) — если хотя бы одно встречается в тексте,
    результат отбрасывается независимо от совпадения по позитивным словам.
    Полезно, чтобы убрать явно нерелевантные результаты (например, страницы
    других авторов с похожим названием курса).
    """
    negative = [w.strip().lower() for w in (negative_keywords or []) if w.strip()]

    if not keywords:
        rules = []
    else:
        rules = []
        for k in keywords:
            k = k.strip().lower()
            if not k:
                continue
            if "," in k:
                words = [w.strip() for w in k.split(",") if w.strip()]
                if words:
                    rules.append(("and", words))
            else:
                rules.append(("phrase", k))

    kept = []
    for item in items:
        haystack = f"{item.get('description', '')} {item.get('url', '')} {item.get('title', '')}".lower()

        if negative and any(neg in haystack for neg in negative):
            continue

        if not rules:
            kept.append(item)
            continue

        matched = False
        for kind, val in rules:
            if kind == "phrase":
                if val in haystack:
                    matched = True
                    break
            else:  # "and"
                if all(word in haystack for word in val):
                    matched = True
                    break
        if matched:
            kept.append(item)
    return kept


def dedupe_by_url(items):
    seen = set()
    kept = []
    for item in items:
        url = item.get("url")
        if url in seen:
            continue
        seen.add(url)
        kept.append(item)
    return kept


def run_pipeline(raw_items, keywords, blocked_domains, negative_keywords=None):
    """Полный пайплайн: исключить официалов -> отфильтровать по ключевым словам
    (с учётом стоп-слов) -> убрать дубли. Возвращает и полный список (после
    исключения официалов, без фильтра по словам), и отфильтрованный."""
    step1 = exclude_blocked_domains(raw_items, blocked_domains)
    all_unique = dedupe_by_url(step1)
    step2 = filter_by_keywords(step1, keywords, negative_keywords)
    step3 = dedupe_by_url(step2)
    return {
        "raw_count": len(raw_items),
        "after_domain_exclude": len(step1),
        "after_keyword_filter": len(step2),
        "after_dedupe": len(step3),
        "results": step3,
        "all_results": all_unique,
    }
