"""Разовый скрипт: добавляет список известных пиратских форумов/сайтов
складчин в справочник «Поиск по сайтам» (data/sites.json). Не создаёт
дублей при повторном запуске — сверяет по домену, а не по точному
совпадению названия.

Запускать так же, как и seed_new_authors.py, из корня проекта:

    python -m backend.seed_pirate_sites

Каждый сайт добавляется с типом «auto» (тот же режим, что уже используется
в интерфейсе по умолчанию) — приложение само разберётся, обычный это сайт
или форум на XenForo, без ручной настройки под каждый домен.

Плейсхолдер-пример из коробки («example-site», «Пример (замените на реальный
сайт)») автоматически удаляется, если он ещё не тронут — чтобы не путался
среди настоящих сайтов. Если вы его уже отредактировали вручную, скрипт
его не тронет (сверяет и id, и название одновременно).
"""
from urllib.parse import urlparse

from . import storage

# Домены как есть, без протокола (кроме двух с полным URL — они так и были
# присланы). Скрипт сам достроит https:// и нормализует.
DOMAINS = [
    "slivap.ru", "infovip.biz", "s16.slivbiz.com", "supersliv.biz",
    "https://www.olx.ua", "sliv-info.biz", "slivkurs.ru", "liveinternet.club",
    "s3.sliwbl.com", "freeskladchina.org", "krusoft.at.ua", "moresliv.net",
    "slivinfokurs.club", "s4.shopkurs.biz", "pirate-buhta.com", "insliv.club",
    "bestkurs.biz", "kursstore.com", "s1.skladchinmore.one", "s3.elitekurs.ru",
    "b1.boominfo.co", "kursclub.net", "xmind.space", "s113.skladchina.in",
    "s9.skladchinakursov.com", "kursi247.ru", "s9.kursi24.org", "pirat.club",
    "itnull.info", "vsekursi24.ru", "kladovayakatalog.ru", "s3.skladchikurs.pro",
    "s3.shopkurs.org", "d3.dolinakursov.pro", "n1.many-courses.net",
    "obzor-kursovzarabotka.ru", "s5.skladchinakurs.biz", "freekurses.site",
    "s1.silasliva.biz", "slivbest.club", "fix-course.ru", "infobank.me",
    "piratebuhta.pw", "info-go.co", "we-sky.net", "oblako-media.ru",
    "s1.slivmk.pro", "tor19.sharewood.me", "s5.eground.org", "s1.courses.forum",
    "s6.skladchina.tv", "4r.azu.la", "s2.vavilon.co", "wedum.ru", "s1.sliv.one",
    "s1.kursosliv.com", "s7.kursliv.org", "pixel-brush.ru", "fxsa.club",
    "s6.vkurse.info", "slivkursov.pro", "topsliv.com", "freesliv.net",
    "s2.izilave.com", "big-money.net", "s16.slivskladru.com", "s3.skladchinas.ru",
    "s61.slivschool.com", "skladchina.net", "s1.otblogerov.com",
    "s14.skladmk.online", "sherwoodacademy.host", "slivbox.cc",
    "s4.vskladchinu.net", "s2.slivtg.com", "m2.mx-style.net",
    "m50.usupovmarket.com", "s29.prosliv.com", "s2.skladchinabiz.ru",
    "s1.blackbiz.store", "s1.kursall.com", "lovekurs.com", "sitekursov.com",
    "itnull.me", "s4.infopoisk.net", "v32.skladchik.org", "s66.zapret.me",
    "s2.infopedia.biz", "slivkursov.me", "s1.skladcnik.com", "skladchikvip.com",
    "s2.slivmax.com", "easykursy.com", "kursoff.net", "s3.infomania.one",
    "s4.skladchik.tv", "sharewood.shop", "coursetrain.net", "yourkurs.online",
    "slivcourses.com", "kurssuperss.space", "bazakursov.net", "s3.slivik.pro",
    "newskladchik.com", "skladchikx.com", "infoskladchina.net", "slivup.info",
    "wlux.net", "skladchina-kz.com", "all-dar.com", "isla-la-tortuga.com",
    "unimys.com", "s4.coyrses24.ru", "slivskladchin.com", "c9.coursx.net",
    "skladchinabiz.me", "s4.slivhelix-24.pro", "secretsupermarket.cc",
    "100kursov.best", "skladchina-ua.com", "forexsklad.org",
    "s7.reskladchina.shop", "s8.sklads.net", "s1.elitecourse.pro",
    "s5.sharewood.tech", "supersliv.tech", "h15.helix-24.biz",
    "s2.skladchinavip.pro", "s10.skladchiki.pro", "s2.moreskladchin.com",
    "kurs.ar", "sub1.sliv.club", "i-tor.pro", "s1.skladchikc.pro",
    "bitforum.one", "newsliv.ru", "s4.shopkurs.net", "s3.skladchinabiz.kz",
    "s1.skladchiksorg.ru", "s1.kladovaya-katalog.ru", "s-2eq.dulinakursov.ru",
    "s1.supersliv.biz", "s-ons.dolinakursov.ru", "https://www.lastcave.com",
    "kursytreningi.com", "s2.skladchina.com", "phphack.ru",
    "s2.skladchinabz.net", "kadets.net", "s2.skladchikscom.net",
    "v3.vskladchinu.com", "slivkursovtg.com", "skladchinabiz.club",
    "skladchikslivy.org", "skladchinaslivy.com", "slivius.cc",
    # найдены вручную в переписке 06.08.2026 — реальные раздачи курса
    # "GPT'S агенты" (Андрианов), которых не было в первоначальном списке
    "sharewood.forum", "skladchinabiz.kz", "znaniyamarket.com",
]

PLACEHOLDER_ID = "example-site"
PLACEHOLDER_NAME = "Пример (замените на реальный сайт)"


def _normalize(domain_or_url):
    """Возвращает (host_без_www_для_сверки, полный_https_url)."""
    raw = domain_or_url.strip()
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = parsed.netloc.lower()
    compare_host = host[4:] if host.startswith("www.") else host
    return compare_host, f"{parsed.scheme}://{host}"


def get_or_create_site(domain_or_url):
    compare_host, full_url = _normalize(domain_or_url)
    for s in storage.load_sites():
        existing_host, _ = _normalize(s["url_template"])
        if existing_host == compare_host:
            return "уже был"
    storage.upsert_site({
        "id": None,
        "name": compare_host,
        "url_template": full_url,
        "type": "auto",
    })
    return "добавлен"


def remove_untouched_placeholder():
    for s in storage.load_sites():
        if s["id"] == PLACEHOLDER_ID and s["name"] == PLACEHOLDER_NAME:
            storage.delete_site(PLACEHOLDER_ID)
            return True
    return False


def main():
    print("Добавляю сайты в справочник «Поиск по сайтам»...\n")
    removed = remove_untouched_placeholder()
    if removed:
        print("Удалён нетронутый пример-плейсхолдер из коробки.\n")

    added, skipped = 0, 0
    for domain in DOMAINS:
        status = get_or_create_site(domain)
        if status == "добавлен":
            added += 1
        else:
            skipped += 1

    print(f"Готово: добавлено {added}, уже было (пропущено) {skipped}, всего в списке {len(DOMAINS)}.")
    print("Перезапустите сервер (если он был запущен) и обновите страницу в браузере.")


if __name__ == "__main__":
    main()
