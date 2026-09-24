"""Подготовка заявления в суд (в формате, которым пользуется Мосгорсуд для
предварительных обеспечительных мер по защите авторских прав в сети —
заполняемого через личный кабинет на сайте суда, отсюда и структура текста
по разделам «для копирования», а не классический печатный документ с
шапкой «В Мосгорсуд»).

Собирает воедино несколько дел одного автора со статусом «в работе» в
один документ: личные данные автора-истца (см. author_personal_data.py —
хранятся зашифрованными, доступны сотруднику только через этот процесс,
не напрямую), сайты и произведения из выбранных дел, статичный правовой
блок (копия формулировки из вашего реального шаблона — п. 57 постановления
Пленума ВС), и раздел с ответчиками/хостингами, который сознательно
оставлен для ручного заполнения (см. обсуждение — автоматический подбор
хостинг-провайдера из справочника не делаем, слишком велик риск ошибиться).
"""
import io
from urllib.parse import urlparse

from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

LEGAL_BASIS_TEXT = (
    "Прошу суд принять решение с учетом п. 57 постановления Пленума Верховного "
    "Суда Российской Федерации от 23.09.2019 № 10 «О применении части четвертой "
    "Гражданского кодекса Российской Федерации», согласно которому в случае "
    "нарушения исключительного права правообладатель вправе осуществлять защиту "
    "нарушенного права любым из способов, перечисленных в статье 12 и пункте 1 "
    "статьи 1252 Гражданского кодекса Российской Федерации, в том числе путем "
    "предъявления требования о пресечении действий, нарушающих право или "
    "создающих угрозу его нарушения; в силу подпункта 2 пункта 1 статьи 1252 "
    "Гражданского кодекса Российской Федерации такое требование может быть "
    "предъявлено не только к лицу, совершающему такие действия или "
    "осуществляющему необходимые приготовления к ним, но и к иным лицам, "
    "которые могут пресечь такие действия."
)

PERSONAL_LABELS = [
    ("full_name", "ФИО, дата рождения"),
    ("birth_place", "Место рождения"),
    ("passport", "Паспорт"),
    ("issued_by", "Кем выдан"),
    ("snils", "СНИЛС"),
]

ORG_LABELS = [
    ("org_name", "Наименование организации"),
    ("org_inn", "ИНН"),
    ("org_kpp", "КПП"),
    ("org_address", "Адрес"),
    ("org_representative", "Представитель"),
]


def _domain_only(url):
    """"https://slivbox.cc/threads/samyj-polnyj-kurs..." -> "slivbox.cc".
    В заявление вставляется только домен, не полный путь страницы — короче
    и читаемее, полный путь странице заявлению не нужен. При сбое разбора
    (совсем не похоже на URL) возвращает исходную строку как есть, не
    роняет формирование документа."""
    if not url:
        return ""
    try:
        host = urlparse(url).hostname
        return host or url
    except Exception:  # noqa
        return url


def _add_heading(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(13)
    return p


def _add_label_value(doc, label, value):
    p = doc.add_paragraph()
    label_run = p.add_run(f"{label}: ")
    label_run.bold = True
    p.add_run(value or "[не указано]")


def build_petition_docx(personal_fields, author_name, cases, attachment_counts=None):
    """personal_fields — словарь из author_personal_data.get(author_id).
    cases — список дел блокировки (со статусом «в работе»), каждое
    должно содержать хотя бы url и work_title.
    attachment_counts — опционально, словарь {ключ: количество файлов},
    см. _ATTACHMENT_LABELS — добавляет в конец документа раздел
    «Приложения» с перечнем и числом прилагаемых файлов. Если не
    передан (None) или все счётчики нулевые — раздел просто не
    добавляется, поведение как раньше.
    Возвращает bytes готового .docx файла.

    Раздел «Заявитель» зависит от personal_fields["entity_type"] —
    "organization" (юридическое лицо), "individual_entrepreneur" (ИП, те
    же поля ORG_LABELS, но с заголовком «Индивидуальный предприниматель»)
    или "individual" (физическое лицо, поля PERSONAL_LABELS — как было
    раньше, это значение по умолчанию для обратной совместимости с уже
    сохранёнными записями, у которых entity_type ещё не проставлен)."""
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title.add_run(
        "Заявление о принятии предварительных обеспечительных мер "
        "по защите авторских прав в информационно-телекоммуникационных сетях"
    )
    title_run.bold = True
    title_run.font.size = Pt(13)
    doc.add_paragraph()

    entity_type = (personal_fields or {}).get("entity_type") or "individual"
    if entity_type == "organization":
        _add_heading(doc, "Юридическое лицо")
        for key, label in ORG_LABELS:
            _add_label_value(doc, label, personal_fields.get(key, ""))
    elif entity_type == "individual_entrepreneur":
        _add_heading(doc, "Индивидуальный предприниматель")
        for key, label in ORG_LABELS:
            _add_label_value(doc, label, personal_fields.get(key, ""))
    else:
        _add_heading(doc, "Физическое лицо")
        for key, label in PERSONAL_LABELS:
            _add_label_value(doc, label, personal_fields.get(key, ""))
    doc.add_paragraph()

    domains = list(dict.fromkeys(_domain_only(c.get("url", "")) for c in cases if c.get("url")))  # без дублей, сохраняя порядок
    works = sorted({c.get("work_title", "") for c in cases if c.get("work_title")})
    urls_text = ", ".join(domains)
    works_text = ", ".join(f"«{w}»" for w in works) if works else "«[не указано]»"

    _add_heading(doc, "Описание нарушения")
    p = doc.add_paragraph()
    p.add_run(
        f"На сайтах {urls_text} без разрешения правообладателя распространяются "
        f"(осуществляются необходимые приготовления к распространению) "
        f"аудиовизуальные произведения {works_text}, являющиеся интеллектуальной "
        f"собственностью истца."
    )
    doc.add_paragraph()

    # Раньше нигде в документе не было полных ссылок на конкретные страницы
    # с нарушением — только доменные имена (например, "zapret.me" вместо
    # "https://zapret.me/threads/..."). Для заявления в суд нужна именно
    # точная страница, не просто домен. Отдельный список: одна ссылка на
    # один пункт, с привязкой к произведению, чтобы не пришлось искать
    # соответствие вручную.
    _add_heading(doc, "Ссылки на нарушения")
    for c in cases:
        url = c.get("url", "")
        if not url:
            continue
        p = doc.add_paragraph()
        work_title = c.get("work_title", "")
        p.add_run(f"«{work_title}»: " if work_title else "").bold = True
        p.add_run(url)
    doc.add_paragraph()

    _add_heading(doc, "Правовое основание")
    doc.add_paragraph(LEGAL_BASIS_TEXT)
    doc.add_paragraph()

    # Раньше здесь была статичная заглушка "[впишите наименование
    # ответчика/ответчиков — см. раздел ниже]" — притом что нужные данные
    # (case["defendant"]) к этому моменту уже есть и используются чуть
    # ниже, в разделе "Ответчики". Собираем те же группы по домену, что и
    # там (см. cases_by_domain), чтобы список ответчиков в "Требовании"
    # точно совпадал с тем, что перечислено в разделе ниже — не задваивать
    # логику группировки в двух местах с риском разойтись.
    cases_by_domain = {}
    domain_order = []
    for c in cases:
        d = _domain_only(c.get("url"))
        if not d:
            continue
        if d not in cases_by_domain:
            cases_by_domain[d] = []
            domain_order.append(d)
        cases_by_domain[d].append(c)
    defendant_names = list(dict.fromkeys(
        cs[0].get("defendant").strip() for cs in cases_by_domain.values() if (cs[0].get("defendant") or "").strip()
    ))
    if defendant_names:
        defendants_text = ", ".join(defendant_names)
    else:
        # Ни у одного из дел ответчик не заполнен — честно оставляем
        # плейсхолдер, а не подставляем пустоту молча.
        defendants_text = "[указать наименование ответчика/ответчиков — см. раздел «Ответчики» ниже]"

    _add_heading(doc, "Требование")
    p = doc.add_paragraph()
    p.add_run(
        f"Запретить ответчикам {defendants_text} создание технических условий, "
        f"обеспечивающих размещение, распространение, приготовление к "
        f"размещению и иное использование аудиовизуальных произведений "
        f"{works_text} правообладателя — {author_name or '[автор не указан]'} "
        f"на сайтах {urls_text} в информационно-телекоммуникационной сети "
        f"«Интернет»."
    )
    doc.add_paragraph()

    _add_heading(doc, "Ответчики (хостинг-провайдеры)")
    for domain in domain_order:
        cs = cases_by_domain[domain]
        first = cs[0]
        p = doc.add_paragraph()
        p.add_run(f"{domain} — ").bold = True
        defendant = first.get("defendant") or "[указать наименование ответчика]"
        ip = first.get("ip_address") or "не определён"
        address = first.get("defendant_address") or "[указать адрес регистрации]"
        p.add_run(f"{defendant} (IP: {ip}, {address})")
        # Полные ссылки сюда намеренно не дублируются — они уже
        # перечислены выше, в разделе «Ссылки на нарушения» (см. заметку
        # разработки, 03.09: раньше один и тот же список URL показывался
        # дважды в разных разделах документа).

    if attachment_counts:
        _add_attachments_section(doc, attachment_counts)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# Порядок и подписи для раздела "Приложения" — единообразно с тем, как
# app.py раскладывает файлы по категориям при сборке zip (см.
# prepare_court_petition): скриншоты нарушения и скриншоты
# подтверждения хостинга/IP считаются и показываются отдельно, потому
# что это разные по назначению доказательства (см. комментарий в
# app.py), даже если оба — просто PNG-снимки.
_ATTACHMENT_LABELS = [
    ("violation_screenshots", "Скриншоты нарушения"),
    ("ip_screenshots", "Скриншоты подтверждения хостинга/IP"),
    ("power_of_attorney", "Доверенность"),
    ("copyright_proof", "Документы, подтверждающие авторство"),
    ("other_author_docs", "Иные документы автора (договор, скан паспорта и т.п.)"),
    ("employee_docs", "Документы специалиста, подающего заявление"),
]


def _add_attachments_section(doc, attachment_counts):
    """attachment_counts — словарь {ключ: количество файлов}, см.
    _ATTACHMENT_LABELS выше для списка ожидаемых ключей. Считается по
    файлам (штукам), не по фактическим страницам внутри многостраничных
    PDF/DOCX — открывать и парсить произвольные форматы ради точного
    числа листов внутри каждого файла не делаем: разные форматы (JPG,
    PDF, DOCX, HEIC) потребовали бы разных библиотек и рисковали бы
    падать на нестандартных/повреждённых файлах прямо в процессе
    формирования заявления. Для одностраничных скриншотов (PNG) число
    файлов и число листов совпадает точно; для документов автора (могут
    быть многостраничными) — это нижняя граница, не точное число листов."""
    total = sum(attachment_counts.get(key, 0) for key, _ in _ATTACHMENT_LABELS)
    if total == 0:
        return
    doc.add_paragraph()
    _add_heading(doc, "Приложения")
    p = doc.add_paragraph()
    p.add_run(
        "К заявлению прилагаются следующие документы (количество указано "
        "в файлах; для многостраничных документов автора — не менее "
        "указанного числа листов):"
    )
    for key, label in _ATTACHMENT_LABELS:
        count = attachment_counts.get(key, 0)
        if count == 0:
            continue
        word = _pluralize_files(count)
        _add_label_value(doc, label, f"{count} {word}")
    # Итоговая строка "Всего приложений: N файлов" убрана по прямой
    # просьбе пользователя (см. заметку разработки, 03.09) — постатейная
    # разбивка выше уже даёт всю нужную информацию, а сквозной итог никак
    # не использовался.


def _pluralize_files(n):
    """1 файл / 2 файла / 5 файлов — обычное русское склонение по числу."""
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return "файл"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "файла"
    return "файлов"
