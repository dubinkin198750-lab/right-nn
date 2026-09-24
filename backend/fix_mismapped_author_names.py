"""Разовый скрипт: находит и (по подтверждению) исправляет дела блокировки,
у которых в поле «Автор» по ошибке записан текст поискового запроса
(matched_query) вместо настоящего имени автора.

Причина бага (уже исправлена в коде — см. frontend/app.js, кнопка «→ В
блокировку» в разделе «Поиск по сайтам»): раньше эта кнопка писала в
author_name текст запроса, которым нашлась ссылка, а не выбранного
автора. Этот скрипт чинит уже накопленные до исправления дела — сам
баг в новых делах больше не появится.

Использование — сначала ДИАГНОСТИКА (ничего не меняет):

    python -m backend.fix_mismapped_author_names

Покажет все значения «Автор», которых нет среди настоящих авторов
(data/authors.json) — с количеством дел и примерами ссылок на каждое.

Дальше — ИСПРАВЛЕНИЕ конкретных значений (пример под уже найденный
случай "GPT's агенты"/"GPT'S агенты" -> Андрианов Евгений Владимирович,
подтверждено по ссылкам, где в самом URL встречается "andrianov"):

    python -m backend.fix_mismapped_author_names --apply \\
        --map "GPT's агенты=Андрианов Евгений Владимирович" \\
        --map "GPT'S агенты=Андрианов Евгений Владимирович"

Можно передать несколько --map за один запуск. Значения, для которых
соответствие не указано явно — не трогаются вообще (безопасно по
умолчанию, ничего не меняется вслепую по догадке).
"""
import argparse

from . import storage


def _real_author_names():
    return {a["name"] for a in storage.load_authors()}


def _orphan_groups(cases, real_names):
    groups = {}
    for c in cases:
        name = (c.get("author_name") or "").strip()
        if not name or name in real_names:
            continue
        groups.setdefault(name, []).append(c)
    return groups


def report():
    real_names = _real_author_names()
    cases = storage.load_blocking_cases()
    archive = storage.load_report_archive()

    for label, items in (("активные дела (data/blocking_cases.json)", cases),
                          ("заархивированные дела (data/report_archive.json)", archive)):
        groups = _orphan_groups(items, real_names)
        print(f"\n=== {label} ===")
        if not groups:
            print("  Подозрительных значений «Автор» не найдено.")
            continue
        for name, group_cases in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            print(f'  «{name}» — {len(group_cases)} дел(а). Примеры ссылок:')
            for c in group_cases[:3]:
                print(f"      {c.get('url')}")
    print(
        "\nЕсли значение выше — на самом деле название произведения/текст "
        "поискового запроса, а не настоящий автор, — запустите скрипт "
        "повторно с --apply и --map \"<это значение>=<настоящий автор>\" "
        "для каждого такого случая."
    )


def apply_fix(mapping):
    real_names = _real_author_names()
    unknown_targets = set(mapping.values()) - real_names
    if unknown_targets:
        print(f"СТОП: этих авторов нет в data/authors.json, проверьте написание: {sorted(unknown_targets)}")
        return

    for store_label, load_fn, save_fn in (
        ("активные дела", storage.load_blocking_cases, storage.save_blocking_cases),
    ):
        items = load_fn()
        changed = 0
        for c in items:
            name = (c.get("author_name") or "").strip()
            if name in mapping:
                c["author_name"] = mapping[name]
                changed += 1
        if changed:
            save_fn(items)
        print(f"{store_label}: исправлено {changed} дел(а).")

    # Архив (report_archive.json) исправляется отдельно — там нет готовой
    # save_report_archive-обёртки под точечное редактирование записей,
    # используем ту же функцию, что и storage.save_report_archive.
    archive = storage.load_report_archive()
    changed = 0
    for c in archive:
        name = (c.get("author_name") or "").strip()
        if name in mapping:
            c["author_name"] = mapping[name]
            changed += 1
    if changed:
        storage.save_report_archive(archive)
    print(f"заархивированные дела: исправлено {changed} дел(а).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="применить исправления (по умолчанию — только отчёт, ничего не меняется)")
    parser.add_argument("--map", action="append", default=[], metavar="ОШИБОЧНОЕ=ПРАВИЛЬНОЕ",
                         help='соответствие "текущее ошибочное значение=настоящее имя автора" — можно указывать несколько раз')
    args = parser.parse_args()

    if not args.apply:
        report()
        return

    if not args.map:
        print("Для --apply нужен хотя бы один --map \"ошибочное=правильное\". Сначала запустите без --apply, чтобы увидеть список.")
        return

    mapping = {}
    for item in args.map:
        if "=" not in item:
            print(f"Пропускаю некорректный --map (нет «=»): {item!r}")
            continue
        wrong, correct = item.split("=", 1)
        mapping[wrong.strip()] = correct.strip()

    apply_fix(mapping)


if __name__ == "__main__":
    main()
