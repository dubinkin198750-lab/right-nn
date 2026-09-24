"""Определение IP-адреса, хостинг-провайдера и email для жалоб по URL/домену.

Работает в два шага:
1. DNS-запрос (socket.gethostbyname) — узнаём IP-адрес домена. Это надёжно
   почти всегда, стандартная библиотека Python, без внешних сервисов.
2. RDAP-запрос (rdap.org — публичный, бесплатный, без API-ключа) — по
   IP-адресу узнаём организацию, на которую зарегистрирована подсеть
   (обычно это и есть хостинг-провайдер: Cloudflare, Hetzner, OVH и т.п.),
   и — отдельно — email контакта с ролью «abuse» (это стандартная роль в
   RDAP именно для жалоб на злоупотребления, у большинства провайдеров
   заполнена и совпадает с тем, что стоило бы вписать в форму жалобы).

Важная оговорка (стоит показывать пользователю): если сайт спрятан за
CDN/защитой (чаще всего это Cloudflare), то и IP, и организация, и email
будут принадлежать именно CDN, а не реальному хостингу сайта за ним —
RDAP технически не может «заглянуть» за CDN. Оба поля в интерфейсе
остаются редактируемыми вручную специально для такого случая.
"""
import re
import socket
from urllib.parse import urlparse

import requests

RDAP_TIMEOUT = 6  # секунд — не даём одному медленному запросу подвесить создание/обновление дела

# Порядок предпочтения ролей entity в RDAP-ответе для названия организации —
# сначала пытаемся найти реального держателя блока (registrant), а не
# первую попавшуюся запись. У RIPE (европейский регистратор) первой в
# списке нередко идёт служебная запись вроде «LIR-LV-...» — технический
# идентификатор регионального регистратора, не название компании.
_ROLE_PRIORITY = ["registrant", "abuse", "administrative", "technical", "registrar"]

# Похоже на служебный технический идентификатор (например, "lir-lv-podacini"
# или "ORG-XY12-RIPE"), а не на человекочитаемое название компании: только
# строчные/прописные буквы, цифры и дефисы, без пробелов. Настоящие названия
# компаний почти всегда содержат пробел или явно читаются как имя
# ("Cloudflare, Inc.", "ООО Хостинг-Сервис").
_HANDLE_LIKE_RE = re.compile(r"^[A-Za-z0-9]+(-[A-Za-z0-9]+)+$")


def _looks_like_technical_handle(name):
    return bool(_HANDLE_LIKE_RE.match(name.strip()))


def _extract_domain(url_or_domain):
    """Принимает как полный URL (https://example.com/page), так и голый домен."""
    value = (url_or_domain or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = "http://" + value
    host = urlparse(value).hostname or ""
    return host.lower()


def resolve_ip(url_or_domain):
    """Возвращает IP-адрес домена или None, если не удалось определить."""
    domain = _extract_domain(url_or_domain)
    if not domain:
        return None
    try:
        return socket.gethostbyname(domain)
    except (socket.gaierror, socket.timeout, UnicodeError):
        return None


def _fetch_rdap(ip):
    """Один HTTP-запрос к rdap.org, возвращает сырой JSON-ответ (dict) или
    None при любой ошибке сети. Вынесено отдельно от разбора, чтобы можно
    было переиспользовать один и тот же ответ и для определения хостинга/
    email, и для поиска официальной страницы регистратора — не делать два
    сетевых похода за одними и теми же данными."""
    try:
        resp = requests.get(f"https://rdap.org/ip/{ip}", timeout=RDAP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError):
        return None


def _parse_rdap_details(data):
    """hosting_org: сначала ищем запись с самой «весомой» ролью (registrant
    прежде всего), пропускаем всё, что похоже на служебный технический
    идентификатор, а не на настоящее название компании; в крайнем случае —
    название сети верхнего уровня (например, «NET-3-60»).

    hosting_address: адрес того же держателя записи — см. _address_from_vcard.
    Есть далеко не всегда (многие провайдеры не публикуют полный адрес в
    WHOIS/RDAP), тогда возвращается None, и поле в интерфейсе остаётся для
    ручного заполнения, как и раньше.

    abuse_email: ищем именно роль «abuse» — стандартная в RDAP роль для
    контакта по злоупотреблениям, обычно у неё и правда заполнен email,
    рабочий для отправки жалобы."""
    if data is None:
        return {"hosting_org": None, "hosting_address": None, "abuse_email": None}

    entities = data.get("entities", [])

    name_candidates = []  # (приоритет_роли, имя)
    address_candidates = []  # (приоритет_роли, адрес)
    abuse_email = None
    for entity in entities:
        roles = entity.get("roles", [])
        priority = min((_ROLE_PRIORITY.index(r) for r in roles if r in _ROLE_PRIORITY), default=len(_ROLE_PRIORITY))
        for vcard_source in [entity] + entity.get("entities", []):
            vcard = vcard_source.get("vcardArray")
            name = _field_from_vcard(vcard, "fn")
            if name and not _looks_like_technical_handle(name):
                name_candidates.append((priority, name))
            address = _address_from_vcard(vcard)
            if address:
                address_candidates.append((priority, address))
            if "abuse" in roles and not abuse_email:
                email = _field_from_vcard(vcard, "email")
                if email:
                    abuse_email = email

    hosting_org = None
    if name_candidates:
        name_candidates.sort(key=lambda c: c[0])
        hosting_org = name_candidates[0][1]
    else:
        # ничего похожего на нормальное название не нашли в entities — берём
        # название самой сети верхнего уровня, даже если оно тоже не очень
        # читаемое — то же самое показывают обычные публичные whois-сервисы
        hosting_org = data.get("name")

    hosting_address = None
    if address_candidates:
        address_candidates.sort(key=lambda c: c[0])
        hosting_address = address_candidates[0][1]

    return {"hosting_org": hosting_org, "hosting_address": hosting_address, "abuse_email": abuse_email}


def _rdap_details(ip):
    """Совместимость с уже написанным кодом/тестами — один запрос + разбор."""
    return _parse_rdap_details(_fetch_rdap(ip))


# Официальные веб-интерфейсы поиска по IP у самих региональных
# регистраторов (RIR) — не через rdap.org-агрегатор, а напрямую у того, кто
# реально ведёт эту базу. Определяем нужный по полю "port43" в ответе
# RDAP — это стандартное поле, прямо указывающее WHOIS-сервер держателя
# записи (например, "whois.ripe.net"). Названия организаций-регистраторов
# читаемы человеком лучше, чем сырой JSON, и это подлинно официальный
# источник, а не посредник.
_RIR_WEB_UI = {
    "whois.ripe.net": ("RIPE NCC", "https://apps.db.ripe.net/db-web-ui/query?searchtext={ip}"),
    "whois.arin.net": ("ARIN", "https://search.arin.net/rdap/?query={ip}"),
    "whois.apnic.net": ("APNIC", "https://wq.apnic.net/apnic-bin/whois.pl?searchtext={ip}"),
    "whois.lacnic.net": ("LACNIC", "https://query.milacnic.lacnic.net/search?key={ip}"),
    "whois.afrinic.net": ("AFRINIC", "https://www.afrinic.net/whois?searchtext={ip}"),
}


def official_registry_url(ip):
    """Возвращает (rir_name, url) официальной страницы регистратора для
    этого IP, или (None, None), если определить не удалось (тогда стоит
    откатиться на rdap.org — хуже с точки зрения «официальности», но хотя
    бы что-то, а не пустая ссылка)."""
    data = _fetch_rdap(ip)
    if not data:
        return None, None
    port43 = (data.get("port43") or "").strip().lower()
    entry = _RIR_WEB_UI.get(port43)
    if not entry:
        return None, None
    rir_name, template = entry
    return rir_name, template.format(ip=ip)


def _field_from_vcard(vcard_array, field_name):
    if not vcard_array or len(vcard_array) < 2:
        return None
    for field in vcard_array[1]:
        # формат каждого поля: ["fn", {}, "text", "Cloudflare, Inc."]
        #                   или ["email", {}, "text", "abuse@example.com"]
        if isinstance(field, list) and len(field) >= 4 and field[0] == field_name:
            return field[3]
    return None


def _address_from_vcard(vcard_array):
    """Адрес держателя записи — подтверждённый реальный формат (проверено
    на настоящем RDAP-ответе ARIN по автономной системе Cloudflare,
    AS13335): поле "adr" встречается в RDAP в двух видах —

    1. Короткая форма — сам адрес уже готовой строкой лежит в параметре
       "label" (второй элемент поля): ["adr", {"label": "101 Townsend
       Street\\nSan Francisco\\nCA\\n94107"}, "text", ["", "", ...]] — так
       заполняет ARIN у крупных провайдеров, именно этот случай и был
       проверен на реальном ответе.
    2. Полная форма — семь отдельных компонентов адреса в четвёртом
       элементе (сам массив значений): [почтовый ящик, доп. адрес, улица,
       город, регион, индекс, страна] — стандартный формат по RFC 6350/7095,
       так может быть у RIPE/APNIC/других регистраторов.

    Пробуем оба варианта по очереди. Возвращает None, если адреса нет ни
    в каком виде — многие провайдеры (особенно с приватностью на WHOIS)
    его просто не публикуют, тогда поле в интерфейсе остаётся ручным, как
    и раньше."""
    if not vcard_array or len(vcard_array) < 2:
        return None
    for field in vcard_array[1]:
        if not (isinstance(field, list) and len(field) >= 4 and field[0] == "adr"):
            continue
        params = field[1] if isinstance(field[1], dict) else {}
        label = params.get("label")
        if label:
            # склеиваем многострочный label в одну строку через запятую —
            # удобнее для однострочного текстового поля в интерфейсе
            parts = [p.strip() for p in str(label).replace("\r\n", "\n").split("\n") if p.strip()]
            if parts:
                return ", ".join(parts)
        components = field[3]
        if isinstance(components, list):
            parts = [str(c).strip() for c in components if isinstance(c, str) and c.strip()]
            if parts:
                return ", ".join(parts)
    return None


def lookup(url_or_domain):
    """Главная функция: возвращает {"ip_address": str, "hosting_org": str,
    "defendant_email": str, "defendant_address": str} — пустая строка там,
    где определить не удалось.

    defendant_address подтягивается из RDAP, если регистратор его
    публикует (проверено на реальном ответе ARIN для Cloudflare — есть) —
    но многие провайдеры (особенно с приватностью WHOIS) его не дают,
    тогда пусто и поле остаётся для ручного заполнения, как раньше.

    Никогда не бросает исключение — при любой ошибке сети/DNS просто
    возвращает пустые строки, чтобы не ломать создание/обновление дела
    из-за недоступности внешнего сервиса.
    """
    ip = resolve_ip(url_or_domain)
    if not ip:
        return {"ip_address": "", "hosting_org": "", "defendant_email": "", "defendant_address": ""}
    details = _rdap_details(ip)
    return {
        "ip_address": ip,
        "hosting_org": details["hosting_org"] or "",
        "defendant_email": details["abuse_email"] or "",
        "defendant_address": details.get("hosting_address") or "",
    }


# Суффиксы организационно-правовой формы — отбрасываются при сравнении,
# чтобы не мешали сопоставлению («ДДОС-Гвард» и «ДДОС-Гвард ЛТД» —
# по сути одно и то же название, форма (LTD/Inc/ООО/...) не несёт
# различительного смысла для проверки «тот ли это ответчик»).
_ORG_SUFFIXES = {
    "inc", "llc", "ltd", "limited", "srl", "gmbh", "corp", "corporation",
    "oy", "ab", "bv", "sa", "spa", "plc", "llp", "co", "company", "network",
    "networks", "solutions", "solution", "hosting", "group", "holdings",
    "systems", "technology", "technologies", "international", "ooo", "ооо",
    "зао", "оао", "ао", "the", "fzco", "fz",
}


def _normalize_org_name(name):
    """Латинская часть названия организации, приведённая к сравнимому
    виду: нижний регистр, без пунктуации и организационно-правовых
    суффиксов. Возвращает список «значимых» слов (обычно 1-2 — как раз
    то, что отличает одну компанию от другой)."""
    latin_only = re.sub(r"[^A-Za-z\s-]", " ", name or "")
    words = re.split(r"[\s-]+", latin_only.lower())
    return [w for w in words if w and w not in _ORG_SUFFIXES and len(w) > 1]


def check_defendant_matches_ip(ip, defendant):
    """Сверяет вручную вписанного «Ответчика» с тем, что по этому IP
    реально показывает RDAP — чтобы поймать случай, когда IP в деле
    поменялся (сайт переехал на другой хостинг), а поле «Ответчик»
    осталось от старого хостинга, и скриншот-подтверждение получится по
    факту не про того ответчика.

    Возвращает {"checked": bool, "matches": bool, "rdap_org": str|None}.
    checked=False — сверить не удалось (нет IP, RDAP недоступен, или в
    названии ответчика нет ни одного латинского слова для сравнения —
    например, значится только кириллицей без RDAP-аналога на латинице) —
    в этом случае предупреждение показывать не нужно, это не то же самое,
    что «не совпадает».

    Сравнение нестрогое (по значимым словам, без организационно-правовой
    формы) — это ожидаемо: RDAP может вернуть чуть другое написание того
    же названия (например, сокращённое «CLOUDFLARENET» вместо «Cloudflare,
    Inc.»), задача — поймать явную ПОДМЕНУ ответчика, а не придираться к
    форматированию.
    """
    if not ip or not defendant:
        return {"checked": False, "matches": True, "rdap_org": None}
    details = _rdap_details(ip)
    rdap_org = details.get("hosting_org") or ""
    if not rdap_org:
        return {"checked": False, "matches": True, "rdap_org": None}  # RDAP недоступен/пуст — не блокируем предупреждением
    defendant_words = _normalize_org_name(defendant)
    if not defendant_words:
        return {"checked": False, "matches": True, "rdap_org": rdap_org}
    rdap_normalized = re.sub(r"[^A-Za-z]", "", rdap_org.lower())
    matches = any(re.sub(r"[^A-Za-z]", "", w) in rdap_normalized for w in defendant_words if len(w) >= 3)
    return {"checked": True, "matches": matches, "rdap_org": rdap_org}


def render_readable_rdap_summary_html(ip, hosting_org, abuse_email, domain=""):
    """Простая читаемая HTML-страница на русском с теми же данными, что уже
    определило приложение — используется как запасной источник для
    скриншота-подтверждения, если основной (2ip.io) недоступен.

    Это НЕ скриншот стороннего сайта — своя собственная свёрстанная
    страница из тех же данных RDAP, которые уже лежат в самом деле
    («Ответчик», «Email ответчика»), без повторного похода в сеть. Раньше
    запасной вариант показывал сырой JSON с rdap.org — нечитаемо для
    человека и не на русском; так честнее и понятнее, при этом прямо
    указано, что это резервный, а не основной путь."""
    import html as html_module

    def esc(value):
        return html_module.escape(str(value) if value else "не определено")

    rows = [
        ("Домен", domain),
        ("IP-адрес", ip),
        ("Организация-держатель блока (по данным RDAP)", hosting_org),
        ("Email для жалоб (abuse)", abuse_email),
    ]
    rows_html = "".join(
        f'<tr><td style="padding:10px 18px;color:#666;border-bottom:1px solid #eee;">{esc(label)}</td>'
        f'<td style="padding:10px 18px;font-weight:600;border-bottom:1px solid #eee;">{esc(value)}</td></tr>'
        for label, value in rows
    )
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>Сводка по IP — данные RDAP</title></head>
<body style="font-family: Arial, sans-serif; padding: 28px; max-width: 720px; color: #222;">
  <h2 style="margin-bottom: 4px;">Сводка по IP-адресу (данные RDAP)</h2>
  <p style="color:#888; font-size: 13px; margin-top: 4px;">
    Запасной источник — основной сервис проверки (2ip.io) был недоступен в момент проверки.
    Данные получены из открытого протокола RDAP (rdap.org) — того же источника,
    которым приложение пользуется для определения ответчика и email.
  </p>
  <table style="border-collapse: collapse; width: 100%; margin-top: 16px;">{rows_html}</table>
</body></html>"""
