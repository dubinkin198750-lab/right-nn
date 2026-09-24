"""Разовый скрипт: добавляет новых авторов и произведения в уже существующую
базу данных приложения (data/authors.json, data/works.json), не трогая то,
что там уже есть (Белоусова, Андрианов и их уже собранные результаты).

Запускать один раз из корня проекта, тем же python/venv, что и сам сервер:

    python -m backend.seed_new_authors

Скрипт «идемпотентный» в разумных пределах:
- Автора с уже существующим именем не создаёт заново — использует того же.
- Произведение с уже существующим у этого автора названием — ОБНОВЛЯЕТ
  (запрос/ключевые слова/исключения), а не дублирует. Это специально нужно
  для «Фабрика клонов» у Андрианова — там просто добавляется домен в
  исключения, само произведение и его уже собранные результаты не трогаются
  (результаты поиска хранятся отдельно, по work_id, а не здесь).
"""
from . import storage

# (имя автора, [ (название произведения, запрос, ключевые_слова, доп_исключения), ... ])
SEED_DATA = [
    (
        "Королева (Фелицына) Наталья",
        [
            (
                "Прически для себя",
                "Фелицына прически для себя скачать",
                ["фелицына, прически", "фелицына, скачать", "фелицына, складчина"],
                ["school.felitsyna.ru", "instagram.com"],
            ),
            (
                "Макияж для себя",
                "Фелицына макияж для себя скачать",
                ["фелицына, макияж", "фелицына, скачать", "фелицына, складчина"],
                ["school.felitsyna.ru"],
            ),
        ],
    ),
    (
        "НПМ Думай",
        [
            (
                "Книга «Думай»",
                "НПМ Думай книга скачать",
                ["думай, книга"],
                ["dum.ai"],
            ),
            (
                "Журнал «Думай»",
                "НПМ Думай журнал скачать",
                ["думай, журнал"],
                ["dum.ai"],
            ),
        ],
    ),
    (
        "Федяев Александр Алексеевич",
        [
            (
                "Онлайн-тренинг «Маркетплейсы 2021»",
                "Федяев Маркетплейсы 2021 скачать",
                ["федяев, маркетплейс", "федяев, скачать", "федяев, складчина"],
                ["alexander-fedyaev.ru"],
            ),
        ],
    ),
    (
        "Андрианов Евгений Владимирович",
        [
            (
                "Специалист по контекстной рекламе с нейросетями",
                "Андрианов специалист по контекстной рекламе с нейросетями скачать",
                ["андрианов, контекстн", "андрианов, реклама", "андрианов, нейросет", "андрианов, скачать"],
                ["info-hit.ru"],
            ),
            (
                "GPT's агенты",
                "Андрианов GPT агенты скачать",
                ["андрианов, агент", "андрианов, gpt", "андрианов, скачать"],
                ["oplata.slems.ru", "academymarketing.ru", "academy-neiro.ru", "neiro-profi.ru", "gotocourse.ru"],
            ),
            (
                # существующее произведение — только добавляем домен в исключения,
                # запрос и ключевые слова не трогаем (заданы вами вручную ранее)
                "«Авторская система по созданию ИИ контент-завода «Фабрика клонов»",
                None,  # None = не менять запрос, если произведение уже есть
                None,  # None = не менять ключевые слова, если произведение уже есть
                ["academymarketing.ru"],  # домен ДОБАВЛЯЕТСЯ к уже имеющимся исключениям
            ),
        ],
    ),
    (
        "Гофман Ольга Сергеевна",
        [
            (
                "Мама-врач",
                "Гофман мама врач скачать",
                ["гофман, мама", "гофман, врач", "гофман, скачать"],
                ["kursmamavrach.com", "kursmamavrach.tilda.ws"],
            ),
            (
                "Интегративная педиатрия",
                "Гофман интегративная педиатрия скачать",
                ["гофман, педиатрия", "гофман, интегратив", "гофман, скачать"],
                ["kursmamavrach.tilda.ws"],
            ),
        ],
    ),
    (
        "Гордынец Иван Сергеевич",
        [
            (
                "Курс «Программист 1С»",
                "Гордынец программист 1С скачать",
                ["гордынец, программист", "гордынец, 1с", "гордынец, скачать"],
                ["ironskills.by", "istudy.by"],
            ),
            (
                "1С:Библиотека стандартных подсистем",
                "Гордынец библиотека стандартных подсистем 1С скачать",
                ["гордынец, библиотека", "гордынец, бсп", "гордынец, скачать"],
                ["v8.1c.ru", "ironskills.by"],
            ),
            (
                "Интеграция и обмен данными в 1С",
                "Гордынец интеграция обмен данными 1С скачать",
                ["гордынец, интеграция", "гордынец, обмен данными", "гордынец, скачать"],
                ["ironskills.by"],
            ),
        ],
    ),
]


def get_or_create_author(name):
    for a in storage.load_authors():
        if a["name"] == name:
            return a, False
    return storage.upsert_author({"id": None, "name": name}), True


def get_work_by_title(author_id, title):
    for w in storage.load_works():
        if w["author_id"] == author_id and w["title"] == title:
            return w
    return None


def add_or_update_work(author_id, title, query, keywords, extra_domains, old_titles=None):
    """old_titles — список прежних названий этого же произведения (если оно
    когда-то называлось иначе): если найдётся по старому названию — просто
    переименует и обновит, а не создаст дубль рядом со старым."""
    existing = get_work_by_title(author_id, title)
    if not existing and old_titles:
        for old_title in old_titles:
            existing = get_work_by_title(author_id, old_title)
            if existing:
                break
    if existing:
        was_renamed = existing["title"] != title
        existing["title"] = title
        if query is not None:
            existing["query"] = query
        if keywords is not None:
            existing["keywords"] = keywords
        merged_domains = sorted(set(existing.get("extra_blocked_domains", [])) | set(extra_domains))
        existing["extra_blocked_domains"] = merged_domains
        storage.upsert_work(existing)
        return "переименовано и обновлено" if was_renamed else "обновлено"
    else:
        storage.upsert_work({
            "id": None,
            "author_id": author_id,
            "title": title,
            "query": query or "",
            "keywords": keywords or [],
            "negative_keywords": [],
            "pages": 10,
            "extra_blocked_domains": extra_domains,
            "active": True,
            "sources": {"yandex": True, "google": False, "avito": False, "telegram": False},
        })
        return "создано"


# Если произведение раньше называлось иначе (и уже могло быть создано под
# старым именем в прошлых запусках этого скрипта) — здесь можно вручную
# сопоставить новое название со старым(и), чтобы скрипт переименовал
# существующую запись вместо того, чтобы создать рядом дубль.
RENAMES = {
    "Специалист по контекстной рекламе с нейросетями": ["Специалист по контекстной рекламе"],
}


def main():
    print("Добавляю авторов и произведения...\n")
    for author_name, works in SEED_DATA:
        author, created = get_or_create_author(author_name)
        print(f"Автор «{author_name}»: {'создан' if created else 'уже был, использую существующего'}")
        for title, query, keywords, extra_domains in works:
            old_titles = RENAMES.get(title)
            status = add_or_update_work(author["id"], title, query, keywords, extra_domains, old_titles=old_titles)
            print(f"  - «{title}»: {status}")
        print()
    print("Готово. Перезапустите сервер (если он был запущен) и обновите страницу в браузере.")


if __name__ == "__main__":
    main()
