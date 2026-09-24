"""Автоматический скриншот страницы для фиксации нарушения — через headless
Chromium (Playwright).

Сохраняет не только картинку, но и:
- точное время снимка (captured_at, unix timestamp — секунда в секунду);
- итоговый URL после всех переходов/редиректов (сайт мог перенаправить
  на другой адрес — важно зафиксировать, что реально открылось);
- HTML-код страницы на момент снимка (отдельным файлом рядом со
  скриншотом) — на случай, если сайт позже изменит контент или закроет
  доступ, HTML остаётся независимым от самой картинки доказательством
  того, что было на странице.

Требует один раз на сервере после установки зависимостей:
    playwright install chromium --with-deps
(сама библиотека ставится через requirements.txt, а браузер — отдельно,
это особенность Playwright: пакет и браузерный движок разделены).
"""
import re
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

NAVIGATION_TIMEOUT_MS = 20_000  # 20 секунд — сайты-нарушители нередко медленные/перегруженные
FORM_ACTION_TIMEOUT_MS = 8_000  # для заполнения формы — короче: если за 8 секунд
# поле/кнопка не нашлись, дальше ждать бессмысленно, сайт либо изменил
# разметку, либо не отвечает

# Best-effort скрытие типовых cookie/промо/логин-баннеров перед снимком —
# многие сайты (в т.ч. VK для неавторизованных посетителей) показывают
# оверлей поверх контента, который затем перекрывает часть доказательства
# на скриншоте. Не гарантирует работу на 100% сайтов (баннеры бывают
# самые разные), но покрывает большинство типовых случаев по общим
# признакам разметки — фиксированное позиционирование + характерные
# имена классов/атрибутов. Сам контент страницы это не трогает (только
# visibility), поэтому если эвристика где-то ошибочно скроет что-то
# лишнее — это не исказит остальной текст на снимке.
_HIDE_OVERLAYS_JS = """
() => {
  const patterns = /cookie|consent|gdpr|banner|promo|popup|overlay|subscribe|paywall|login-?nag|auth-?nag/i;
  document.querySelectorAll('body *').forEach((el) => {
    const style = window.getComputedStyle(el);
    if (style.position !== 'fixed' && style.position !== 'sticky') return;
    const rect = el.getBoundingClientRect();
    const looksLikeBanner = rect.width >= window.innerWidth * 0.5 && rect.height > 0 && rect.height < window.innerHeight * 0.5;
    const attrs = (el.className + ' ' + el.id).toString();
    if (looksLikeBanner && patterns.test(attrs)) {
      el.style.setProperty('display', 'none', 'important');
    }
  });
}
"""


class ScreenshotCaptureError(Exception):
    """Понятная пользователю ошибка — текст идёт прямо в интерфейс."""


# Признаки того, что реальная страница-нарушение так и не открылась —
# вместо неё браузер получил либо собственную страницу ошибки Chromium
# (нет ни ошибки Playwright, ни исключения — навигация формально
# "успешна", просто ведёт в чёрный экран), либо явную защиту от ботов
# (капча, Cloudflare-проверка и т.п.). Раньше такие снимки тихо
# сохранялись как обычное доказательство — на скрине оказывался либо
# пустой экран, либо "Подтвердите, что вы не робот" вместо реального
# контента (см. заметку разработки, 03.09 — реальные найденные примеры).
_INTERNAL_BROWSER_SCHEMES = ("chrome-error://", "chrome://", "about:blank", "data:text/html,chromewebdata")

_BOT_WALL_MARKERS = (
    "подтвердите, что вы не робот", "i'm not a robot", "im not a robot",
    "verify you are human", "checking your browser", "just a moment",
    "проверка браузера", "access denied", "доступ запрещён", "доступ ограничен",
    "cf-browser-verification", "attention required! | cloudflare",
    "captcha",
)


_SCRIPT_OR_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def looks_like_bot_wall(html):
    """Грубая эвристика — страница похожа на антибот-проверку/капчу, а не
    на настоящий контент. Не идеальна (полностью надёжного способа не
    существует без реального решения капчи), поэтому используется только
    как ПРЕДУПРЕЖДЕНИЕ в описании снимка, не как жёсткий отказ — снимок
    капчи тоже может быть полезен как факт (сайт жив, но защищён), просто
    сотрудник должен понимать, что это не сам пиратский контент."""
    if not html:
        return False
    # Раньше здесь проверялась длина СЫРОГО html целиком — но у настоящих
    # современных антибот-страниц (Cloudflare Turnstile, reCAPTCHA и
    # подобных) внутри часто очень много встроенного JavaScript, из-за
    # чего сырой HTML легко перешагивает любой разумный порог, хотя
    # видимого пользователю текста там — одна строка (см. заметку
    # разработки, 04.09 — реальный найденный случай на живом сервере,
    # где капча так и не была распознана именно по этой причине). Теперь
    # длина считается по тексту БЕЗ <script>/<style> и остальных тегов —
    # у настоящей капчи этот текст всегда короткий, независимо от того,
    # сколько там JS-кода под капотом.
    without_scripts = _SCRIPT_OR_STYLE_RE.sub(" ", html)
    visible_text = _TAG_RE.sub(" ", without_scripts)
    lowered_full = html.lower()  # маркеры ищем по всему HTML — фраза может быть в атрибуте/JSON, не только в видимом тексте
    if len(visible_text) > 4_000:
        return False
    return any(marker in lowered_full for marker in _BOT_WALL_MARKERS)


def _looks_like_internal_error_page(url):
    if not url:
        return True
    return url.startswith(_INTERNAL_BROWSER_SCHEMES)


def capture(url):
    """Открывает url в headless-браузере, возвращает:
    {"png_bytes": bytes, "html": str, "captured_url": str, "captured_at": float}

    Бросает ScreenshotCaptureError с понятным текстом при любой проблеме
    (страница не открылась, таймаут и т.п.) — вызывающий код показывает
    это сообщение пользователю как есть.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
                try:
                    page.goto(url, wait_until="networkidle")
                except PlaywrightTimeoutError:
                    # страница технически открылась, но не «успокоилась» за отведённое
                    # время (например, из-за постоянно обновляющейся рекламы) —
                    # снимок всё равно делаем тем, что успело отрисоваться,
                    # это лучше, чем ничего.
                    pass
                try:
                    page.evaluate(_HIDE_OVERLAYS_JS)
                except Exception:
                    pass  # эвристика необязательна — если не сработала, просто снимаем как есть
                captured_at = time.time()
                png_bytes = page.screenshot(full_page=True, type="png")
                html = page.content()
                captured_url = page.url
            finally:
                browser.close()
    except PlaywrightTimeoutError as e:
        raise ScreenshotCaptureError(f"Сайт не ответил вовремя: {e}") from e
    except Exception as e:  # noqa — любая ошибка Playwright/сети превращается в понятный текст
        raise ScreenshotCaptureError(f"Не удалось открыть страницу: {e}") from e

    # Раньше на этом моменте функция просто возвращала результат — даже
    # если page.goto() формально прошла без исключения, но браузер внутри
    # себя тихо перешёл на собственную страницу ошибки (chrome-error://
    # и подобное). Playwright в части таких случаев НЕ бросает исключение
    # (see заметку разработки, 03.09 — реальный пойманный пример:
    # captured_url оказался буквально "chrome-error://chromewebdata/",
    # снимок при этом сохранялся как обычный, будто страница открылась).
    if _looks_like_internal_error_page(captured_url):
        raise ScreenshotCaptureError(f"Страница не открылась — браузер получил внутреннюю страницу ошибки ({captured_url or 'пусто'})")

    return {
        "png_bytes": png_bytes,
        "html": html,
        "captured_url": captured_url,
        "captured_at": captured_at,
    }


def capture_with_form_query(url, query_value, input_selectors, submit_selectors):
    """Как capture(), но для сайтов, где результат появляется только после
    заполнения формы и нажатия кнопки (а не сразу по прямой ссылке с
    параметром в URL) — например, русскоязычные whois-сервисы вроде 2ip.io.

    input_selectors / submit_selectors — списки CSS/текстовых селекторов,
    пробуются по очереди, берётся первый видимый подходящий элемент. Это
    осознанная защита от хрупкости: сайт, которым мы не управляем, может
    в любой момент поменять разметку формы — несколько вариантов повышают
    шанс, что автоматизация продолжит работать, но полной гарантии дать
    невозможно, это принципиальное ограничение работы со сторонним сайтом,
    а не с открытым API вроде RDAP.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
                # Единый короткий таймаут по умолчанию для ВСЕХ действий
                # (fill/click/is_visible без явного timeout) — без этого
                # каждое такое действие могло бы независимо ждать до 30
                # секунд (стандартное значение Playwright), и на сайте с
                # рекламой/счётчиками, которые никогда не «затихают»
                # полностью, суммарное время могло растянуться на минуту+.
                page.set_default_timeout(FORM_ACTION_TIMEOUT_MS)
                try:
                    # "domcontentloaded", не "networkidle" — вторая стратегия
                    # ждёт полного затишья сети, а сайты с рекламой и
                    # счётчиками могут никогда не «затихнуть» до конца.
                    page.goto(url, wait_until="domcontentloaded")
                except PlaywrightTimeoutError:
                    pass

                filled = False
                for selector in input_selectors:
                    try:
                        locator = page.locator(selector).first
                        if locator.is_visible(timeout=FORM_ACTION_TIMEOUT_MS):
                            locator.fill(query_value)
                            filled = True
                            break
                    except Exception:  # noqa — пробуем следующий вариант селектора
                        continue
                if not filled:
                    raise ScreenshotCaptureError(
                        "Не удалось найти поле ввода на странице — вероятно, сайт изменил разметку формы. "
                        "Сделайте скриншот вручную и загрузите его через «Загрузить» в этом же окне."
                    )

                clicked = False
                for selector in submit_selectors:
                    try:
                        locator = page.locator(selector).first
                        if locator.is_visible(timeout=FORM_ACTION_TIMEOUT_MS):
                            locator.click()
                            clicked = True
                            break
                    except Exception:  # noqa
                        continue
                if not clicked:
                    raise ScreenshotCaptureError(
                        "Не удалось найти кнопку отправки формы на странице — вероятно, сайт изменил разметку. "
                        "Сделайте скриншот вручную и загрузите его через «Загрузить» в этом же окне."
                    )

                try:
                    # "load", не "networkidle" — та же причина, что и выше.
                    page.wait_for_load_state("load", timeout=FORM_ACTION_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    pass
                # результат обычно дорисовывается через JS уже после события
                # "load" — короткая фиксированная пауза вместо ожидания
                # полного затишья сети, предсказуемая по времени.
                page.wait_for_timeout(1500)

                captured_at = time.time()
                png_bytes = page.screenshot(full_page=True, type="png")
                html = page.content()
                captured_url = page.url
            finally:
                browser.close()
    except ScreenshotCaptureError:
        raise
    except PlaywrightTimeoutError as e:
        raise ScreenshotCaptureError(f"Сайт не ответил вовремя: {e}") from e
    except Exception as e:  # noqa
        raise ScreenshotCaptureError(f"Не удалось получить результат с формы: {e}") from e

    if _looks_like_internal_error_page(captured_url):
        raise ScreenshotCaptureError(f"Страница не открылась — браузер получил внутреннюю страницу ошибки ({captured_url or 'пусто'})")

    return {
        "png_bytes": png_bytes,
        "html": html,
        "captured_url": captured_url,
        "captured_at": captured_at,
    }
