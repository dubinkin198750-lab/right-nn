"""«Постоянно блокируемые ссылки» — авторы, у которых один и тот же
базовый домен всплывает повторно под разными ссылками (обычно с
меняющимся поддоменом-«зеркалом»: s69.zapret.me, s68.zapret.me,
s67.zapret.me... — сам сайт, домен один и тот же, а конкретный URL и
даже поддомен каждый раз новый).

Если считать по полному хосту (s69.zapret.me != s68.zapret.me) —
паттерн вообще не ловится, каждое зеркало выглядит как отдельный,
впервые встреченный сайт. Поэтому группируем по БАЗОВОМУ домену
(последние 2 части адреса, с поправкой на составные зоны вроде .co.uk),
а не по полному хосту.

Группировка — по (автор, произведение, базовый домен), НЕ просто
(автор, домен). Раньше (до 03.09) считали просто по домену+автору — на
маленьких выделенных сайтах-зеркалах это работало правильно, но на
больших многотематических площадках (VK, форумы-агрегаторы вроде
skladchinmore.cc, где под одним доменом легально живут тысячи разных
тем/товаров разных авторов) это ошибочно помечало «хроническим» просто
два РАЗНЫХ товара одного автора на одной большой площадке — а не
реальный случай, когда ОДИН И ТОТ ЖЕ курс повторно всплывает на том же
сайте под новым адресом. Учёт произведения устраняет это: два разных
курса одного автора на одной площадке больше не считаются повторами
друг друга, даже если домен совпадает.

Порог и охват выбраны по умолчанию (можно поменять константы ниже, без
переписывания логики):
  - CHRONIC_THRESHOLD = 2 — домен считается «постоянно блокируемым» уже
    при втором повторении у того же автора/произведения, не дожидаясь
    третьего и далее.
  - Считается вся история целиком (активные дела блокировки + уже
    заархивированные по завершённым месяцам) — иначе после «Завершить
    месяц и заархивировать» счётчик обнулялся бы каждый месяц, теряя
    как раз тот паттерн, ради которого эта фича нужна.
"""
from collections import defaultdict

from . import storage
from . import netinfo

CHRONIC_THRESHOLD = 2

# Составные зоны, где «последние 2 части адреса» дают неверный базовый
# домен (например, для site.co.uk наивный разбор по последним двум
# частям вернул бы "co.uk" — зону, а не домен сайта). Список не
# исчерпывающий (полный список составных зон — это отдельная база,
# т.н. Public Suffix List), но покрывает распространённые случаи;
# для доменов вне этого списка (подавляющее большинство пиратских
# сайтов — обычные .com/.net/.ru/.me/.cc/.xyz и т.п.) разбор по
# последним двум частям корректен всегда.
_MULTI_PART_TLDS = {
    "co.uk", "org.uk", "net.uk", "ac.uk", "gov.uk",
    "co.jp", "ne.jp", "or.jp",
    "com.br", "com.au", "com.tr", "com.ua", "com.cn",
    "co.in", "co.nz", "co.za", "co.kr",
}


def _base_domain(hostname):
    """"s69.zapret.me" -> "zapret.me"; "example.co.uk" -> "example.co.uk"
    (не "co.uk" — составная зона не считается доменом сама по себе)."""
    hostname = (hostname or "").lower().strip(".")
    if not hostname:
        return ""
    parts = hostname.split(".")
    if len(parts) <= 2:
        return hostname
    last_two = ".".join(parts[-2:])
    if last_two in _MULTI_PART_TLDS and len(parts) >= 3:
        return ".".join(parts[-3:])
    return last_two


def _work_key(case):
    """Ключ произведения для группировки — по work_title, не по work_id:
    у дел, добавленных вручную или из старого импорта, work_id может
    отсутствовать, а work_title заполнено почти всегда (и это то самое
    название, которое видно в интерфейсе, естественная связка)."""
    return (case.get("work_title") or "Без произведения").strip() or "Без произведения"


def _all_cases_with_history_flag():
    """Активные дела блокировки + записи из архива отчётов — с общим
    полем is_archived, чтобы дальше можно было ссылаться на источник
    записи (для отображения) не теряя, откуда она взялась."""
    for c in storage.load_blocking_cases():
        yield {**c, "_archived": False}
    for c in storage.load_report_archive():
        yield {**c, "_archived": True}


def compute_chronic_domains(threshold=CHRONIC_THRESHOLD):
    """Возвращает список словарей вида:
    {
      "author_name": "...",
      "work_title": "...",
      "base_domain": "zapret.me",
      "count": 4,              # активные + заархивированные вместе — от этого зависит порог
      "active_case_ids": [...],   # id дел из data/blocking_cases.json — рендерятся полноценными
                                   # интерактивными строками на фронтенде (там уже есть все поля)
      "archived_count": 1,        # сколько из "count" — уже заархивированные по месяцам записи;
                                   # для них отдельных интерактивных действий не показываем (это
                                   # закрытые дела, дальнейшая работа по ним не ведётся), только
                                   # само число учитывается в счётчике повторов
    }
    — только те группы (автор, произведение, базовый домен), где число
    повторов >= threshold. Отсортировано по количеству повторов (по
    убыванию), затем по имени автора.
    """
    groups = defaultdict(list)
    for c in _all_cases_with_history_flag():
        author = (c.get("author_name") or "Без автора").strip() or "Без автора"
        work_title = _work_key(c)
        url = c.get("url") or ""
        domain = _base_domain(netinfo._extract_domain(url))
        if not domain:
            continue
        groups[(author, work_title, domain)].append(c)

    result = []
    for (author, work_title, domain), cases in groups.items():
        if len(cases) < threshold:
            continue
        cases_sorted = sorted(cases, key=lambda c: c.get("added_at") or 0)
        active_ids = [c["id"] for c in cases_sorted if not c.get("_archived") and c.get("id")]
        archived_count = sum(1 for c in cases_sorted if c.get("_archived"))
        result.append({
            "author_name": author,
            "work_title": work_title,
            "base_domain": domain,
            "count": len(cases_sorted),
            "active_case_ids": active_ids,
            "archived_count": archived_count,
        })

    result.sort(key=lambda g: (-g["count"], g["author_name"].lower()))
    return result


def chronic_active_case_ids(threshold=CHRONIC_THRESHOLD):
    """Множество id всех активных дел, входящих хоть в одну "постоянно
    блокируемую" группу — используется, чтобы убрать их из обычной
    таблицы "Блокировка" (см. app.py, /api/blocking-cases) и отдавать
    только через отдельный раздел."""
    ids = set()
    for group in compute_chronic_domains(threshold):
        ids.update(group["active_case_ids"])
    return ids


def count_domain_occurrences(author_name, work_title, url):
    """Сколько раз базовый домен этой ссылки уже встречался у этого же
    автора И ЭТОГО ЖЕ ПРОИЗВЕДЕНИЯ (включая саму эту ссылку, если она уже
    сохранена) — считается по всей истории (активные + заархивированные),
    тем же способом, что и в compute_chronic_domains, но без построения
    всех групп сразу — для разового вызова сразу после создания одного
    дела дешевле посчитать только нужную тройку (автор, произведение,
    домен).

    Возвращает (count, domain) — domain может быть "", если у ссылки не
    удалось определить хост (тогда count всегда 0, ссылка ни в какую
    "постоянно блокируемую" группу попасть не может)."""
    author_name = (author_name or "Без автора").strip() or "Без автора"
    work_title = (work_title or "Без произведения").strip() or "Без произведения"
    domain = _base_domain(netinfo._extract_domain(url or ""))
    if not domain:
        return 0, ""
    count = 0
    for c in _all_cases_with_history_flag():
        a = (c.get("author_name") or "Без автора").strip() or "Без автора"
        if a != author_name or _work_key(c) != work_title:
            continue
        d = _base_domain(netinfo._extract_domain(c.get("url") or ""))
        if d == domain:
            count += 1
    return count, domain


def active_cases_for_domain(author_name, work_title, domain):
    """Все АКТИВНЫЕ (не заархивированные) дела этого автора И ЭТОГО ЖЕ
    ПРОИЗВЕДЕНИЯ на этом базовом домене — целиком, а не только id.
    Используется для ретроактивной досылки автоскриншотов: когда домен
    только что пересёк порог «постоянно блокируемого», в группе обычно
    уже есть более ранние ссылки, добавленные ДО того, как домен стал
    считаться хроническим — раньше автоскриншот срабатывал только для
    той ссылки, что как раз довела счётчик до порога, а более старые
    ссылки того же домена так и оставались без скриншота (см. заметку
    разработки, самокритика от 01.09 — реальный найденный пробел, не
    гипотетический)."""
    author_name = (author_name or "Без автора").strip() or "Без автора"
    work_title = (work_title or "Без произведения").strip() or "Без произведения"
    result = []
    for c in storage.load_blocking_cases():
        a = (c.get("author_name") or "Без автора").strip() or "Без автора"
        if a != author_name or _work_key(c) != work_title:
            continue
        d = _base_domain(netinfo._extract_domain(c.get("url") or ""))
        if d == domain:
            result.append(c)
    return result
