"""Печать информационной плашки прямо на картинке скриншота — не только
в метаданных базы, а буквально впечатано в сам файл изображения.

Причина: скриншот официальной страницы регистратора (RIPE/ARIN/APNIC/...)
сам по себе показывает данные по IP, но не показывает домен, ответчика
одним взглядом и не показывает дату фиксации — человеку, впервые
смотрящему на файл (например, судье), непонятно, что и когда именно
проверялось. Плашка сверху решает это: домен, IP, ответчик, источник и
точная дата/время — в одном кадре, не расходится в поисках по разным
полям базы.

Шрифт (DejaVu Sans, поддерживает кириллицу) лежит прямо в проекте
(backend/assets/), а не берётся из системных шрифтов — иначе на Windows,
где путь к шрифтам совсем другой, плашка либо не отрисовалась бы вообще,
либо кириллица превратилась бы в прямоугольники.

Дата и время фиксации всегда печатаются в московском времени (UTC+3,
MSK) — независимо от того, в каком часовом поясе физически настроен
сервер (хостинг может быть где угодно, в том числе с системным временем
UTC). Раньше использовалось системное время сервера (time.localtime) —
если сервер стоит не в MSK, дата на скриншоте могла не совпадать с
реальным московским временем фиксации. Смещение +3:00 задано явно,
фиксированной константой (datetime.timezone), а не через системную базу
часовых поясов — работает одинаково на любом сервере, без зависимости от
того, установлен ли там пакет tzdata."""
import io
import os
import time
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont

# Московское время — фиксированное смещение UTC+3, не зависит от настроек
# часового пояса сервера и не подвержено переходу на летнее/зимнее время
# (в России с 2014 года его нет, смещение круглый год одно и то же).
MSK_TZ = timezone(timedelta(hours=3), name="MSK")


def format_msk(captured_at):
    """captured_at — unix-время (float/int). Возвращает строку вида
    '20.08.2026 14:05:03 MSK' — всегда московское время, вне зависимости
    от часового пояса сервера, на котором выполняется код."""
    dt = datetime.fromtimestamp(captured_at, tz=MSK_TZ)
    return dt.strftime("%d.%m.%Y %H:%M:%S") + " MSK"

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_FONT_REGULAR = os.path.join(_ASSETS_DIR, "DejaVuSans.ttf")
_FONT_BOLD = os.path.join(_ASSETS_DIR, "DejaVuSans-Bold.ttf")

_FONT_SIZE = 16
_LINE_HEIGHT = 22
_PADDING = 12
_BG_COLOR = (255, 255, 255)
_TEXT_COLOR = (20, 20, 20)
_LABEL_COLOR = (90, 90, 90)


def _load_font(bold=False, size=_FONT_SIZE):
    path = _FONT_BOLD if bold else _FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        # шрифт из проекта не нашёлся (например, файл случайно не попал в
        # архив при переносе) — не роняем всю функцию, просто плашка будет
        # менее аккуратной (стандартный растровый шрифт Pillow, кириллицу
        # тоже поддерживает начиная с современных версий Pillow)
        return ImageFont.load_default()


def stamp_banner(png_bytes, fields, captured_at=None):
    """fields — список пар (подпись, значение), например:
        [("Домен", "example.com"), ("IP-адрес", "1.2.3.4"), ...]
    Пустые/отсутствующие значения пропускаются, лишняя строка не рисуется.

    Возвращает новые PNG-байты — исходное изображение целиком остаётся под
    плашкой, ничего из самого скриншота не обрезается и не перекрывается."""
    lines = [(label, str(value)) for label, value in fields if value]
    if captured_at is None:
        captured_at = time.time()
    lines.append(("Дата и время фиксации", format_msk(captured_at)))

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    width, height = img.size

    banner_height = _PADDING * 2 + _LINE_HEIGHT * len(lines)
    canvas = Image.new("RGB", (width, height + banner_height), _BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    font_label = _load_font(bold=True)
    font_value = _load_font(bold=False)

    y = _PADDING
    for label, value in lines:
        draw.text((_PADDING, y), f"{label}:", fill=_LABEL_COLOR, font=font_label)
        label_width = draw.textlength(f"{label}: ", font=font_label)
        draw.text((_PADDING + label_width, y), value, fill=_TEXT_COLOR, font=font_value)
        y += _LINE_HEIGHT

    # тонкая линия-разделитель между плашкой и самим скриншотом
    draw.line([(0, banner_height - 1), (width, banner_height - 1)], fill=(210, 210, 210), width=1)

    canvas.paste(img, (0, banner_height))

    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


_COMBINE_SEPARATOR_COLOR = (150, 40, 40)  # заметная тёмно-красная полоса — граница между разными скриншотами
_COMBINE_SEPARATOR_HEIGHT = 6


def combine_vertically(png_bytes_list):
    """Склеивает несколько PNG в один файл, один под другим сверху вниз —
    используется при подготовке заявления по нескольким выделенным
    ссылкам (см. app.py, _build_petition_zip): вместо кучи отдельных
    файлов скриншотов нарушений/IP-хостинга получаются 2 файла на всё
    заявление (по прямой просьбе пользователя, 03.09).

    Каждый исходный скриншот уже содержит собственную информационную
    плашку (домен/IP/дата — см. stamp_banner выше), поэтому отдельные
    подписи между сегментами не нужны — просто заметная разделительная
    полоса, чтобы визуально не перепутать конец одного скриншота с
    началом следующего.

    Ширина у разных скриншотов может отличаться (разные сайты, разная
    высота страницы при full_page=True не единственная переменная — сама
    ширина viewport одна и та же, 1366px, но на всякий случай не
    полагаемся на это и приводим все изображения к ширине самого
    широкого) — узкие масштабируются вверх с сохранением пропорций, а
    не просто дополняются пустым полем, чтобы не оставлять на итоговой
    картинке участков, за которые как будто «стыдно» (пустое поле сбоку
    выглядит как обрезанный/битый файл, увеличение — нет).

    Если список пуст — возвращает None (вызывающий код просто не
    добавляет файл в архив вообще, а не кладёт пустую картинку)."""
    if not png_bytes_list:
        return None
    images = []
    for b in png_bytes_list:
        try:
            images.append(Image.open(io.BytesIO(b)).convert("RGB"))
        except Exception:  # noqa — один битый/повреждённый файл на диске не
            # должен рушить всю склейку и всё заявление целиком; остальные
            # снимки в списке всё равно валидны и не должны из-за этого
            # потеряться. Тихого молчания достаточно — сама причина
            # (файл не открылся) уже будет видна по тому, что скриншотов
            # в итоговой картинке меньше, чем ожидалось.
            continue
    if not images:
        return None
    if len(images) == 1:
        out = io.BytesIO()
        images[0].save(out, format="PNG")
        return out.getvalue()

    target_width = max(img.width for img in images)
    resized = []
    for img in images:
        if img.width != target_width:
            new_height = round(img.height * (target_width / img.width))
            img = img.resize((target_width, new_height), Image.LANCZOS)
        resized.append(img)

    total_height = sum(img.height for img in resized) + _COMBINE_SEPARATOR_HEIGHT * (len(resized) - 1)
    canvas = Image.new("RGB", (target_width, total_height), (255, 255, 255))
    y = 0
    for i, img in enumerate(resized):
        canvas.paste(img, (0, y))
        y += img.height
        if i < len(resized) - 1:
            draw = ImageDraw.Draw(canvas)
            draw.rectangle([(0, y), (target_width, y + _COMBINE_SEPARATOR_HEIGHT)], fill=_COMBINE_SEPARATOR_COLOR)
            y += _COMBINE_SEPARATOR_HEIGHT

    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()
