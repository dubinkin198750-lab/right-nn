"""Разовый скрипт: переносит в архив отчётов дела, которые уже стали
«заблокировано» ДО того, как появилась автоматическая архивация (см.
app.py, _maybe_auto_archive_blocked_case — добавлено 01.09.2026).

Автоматическая архивация срабатывает только в момент сохранения решения
через форму — она не сканирует задним числом уже существующие дела. Если
решение «заблокировано» было проставлено ещё до появления этой функции
(например, из старого Excel-импорта или просто раньше сегодняшнего
обновления) — такое дело так и останется висеть в активной «Блокировке»
навсегда, если его не тронуть повторно вручную. Этот скрипт закрывает
этот пробел одним проходом по уже существующим данным.

Использование — сначала ДИАГНОСТИКА (ничего не меняет):

    python -m backend.archive_already_blocked_cases

Покажет список дел, которые попадут в архив, если запустить с --apply —
с именем автора, ссылкой и решением, из-за которого дело считается
заблокированным.

Дальше — реальный перенос:

    python -m backend.archive_already_blocked_cases --apply

Дате блокировки, если она ещё не заполнена, подставляется сегодняшнее
число — по тому же правилу, что и при обычном сохранении через форму
(см. app.py, update_blocking_case) — без неё фоновый мониторинг не сможет
отслеживать, не «ожила» ли ссылка снова."""
import argparse
import time

from . import storage, link_check, reports


def _find_candidates():
    """Активные дела, которые уже подходят под условие архивации
    (заблокировано хотя бы на одном из трёх этапов, needs_resend не
    стоит), но ещё не были заархивированы — то есть всё ещё лежат в
    data/blocking_cases.json."""
    return [c for c in storage.load_blocking_cases() if link_check.is_blocked(c) and not c.get("needs_resend")]


def _blocked_reason(case):
    for field, label in (
        ("claim_decision", "претензия"),
        ("first_appeal_decision", "1-е обращение"),
        ("repeat_appeal_decision", "повторное обращение"),
    ):
        if case.get(field) == "заблокировано":
            return label
    return "?"


def report():
    candidates = _find_candidates()
    if not candidates:
        print("Дел, требующих переноса в архив, не найдено — всё уже в порядке.")
        return
    print(f"Найдено дел для переноса в архив: {len(candidates)}\n")
    for c in candidates:
        missing_date = "" if c.get("block_date") else " (даты блокировки нет — будет подставлено сегодняшнее число)"
        print(f"  «{c.get('author_name', '')}» — {c.get('url', '')} — заблокировано на этапе «{_blocked_reason(c)}»{missing_date}")
    print("\nЗапустите повторно с --apply, чтобы реально перенести эти дела в архив отчётов.")


def apply_fix():
    candidates = _find_candidates()
    if not candidates:
        print("Дел, требующих переноса в архив, не найдено — всё уже в порядке.")
        return

    authors_by_name = {a["name"]: a for a in storage.load_authors()}
    archived_count = 0
    for case in candidates:
        # Та же автоподстановка даты блокировки, что и при обычном
        # сохранении через форму (см. app.py, update_blocking_case) — без
        # неё фоновый мониторинг не сможет отслеживать архивную запись.
        if not case.get("block_date"):
            case["block_date"] = time.strftime("%Y-%m-%d")
            storage.update_blocking_case(case["id"], {"block_date": case["block_date"]})

        author = authors_by_name.get(case.get("author_name", ""))
        start_day = (author or {}).get("report_period_start_day", 1)
        year, month = reports.resolve_report_period(start_day)
        storage.archive_reported_cases([case], year, month)
        print(f"  перенесено: «{case.get('author_name', '')}» — {case.get('url', '')} -> архив {year:04d}-{month:02d}")
        archived_count += 1

    print(f"\nГотово. Перенесено в архив дел: {archived_count}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="реально перенести дела в архив (по умолчанию — только отчёт, ничего не меняется)")
    args = parser.parse_args()

    if args.apply:
        apply_fix()
    else:
        report()


if __name__ == "__main__":
    main()
