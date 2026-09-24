"""Перенос старых полей обращений в новый список appeals (обновление 23.09).

ДАННЫЕ НЕ ТЕРЯЮТСЯ — как это обеспечено:
  1. Перед записью скрипт сам делает копии файлов
     data/blocking_cases.json и data/report_archive.json рядом с ними
     (…json.before-appeals-ГГГГММДД-ЧЧММСС).
  2. В каждом переносимом деле исходные значения старых полей
     сохраняются целиком в поле legacy_appeal_fields_backup — даже если
     разбор «04.08 2И-6684» на дату и номер где-то ошибётся, оригинал
     остаётся в деле.
  3. Старые поля не удаляются: они продолжают существовать (как копия
     нового списка), поэтому прежняя версия программы тоже их читает.
  4. После записи скрипт перечитывает файлы и проверяет: те же дела (по
     id и количеству), у каждого перенесённого есть копия исходных
     значений, совпадающая с оригиналом, и ни одно другое поле дела
     (ссылка, ответчик, примечания, скриншоты, даты претензий...) не
     изменилось. Если хоть что-то не так — файлы автоматически
     возвращаются из копий.
  5. Скрипт можно запускать повторно: уже перенесённые дела он не трогает.

Сначала диагностика (ничего не меняет):

    python -m backend.migrate_appeals

Затем запись:

    python -m backend.migrate_appeals --apply

Запускать при ОСТАНОВЛЕННОМ сервисе приложения.
"""
import argparse
import copy
import json
import os
import re
import shutil
import time

from . import storage, link_check
from . import appeals as appeals_mod

_NUMBER_IN_NOTES = re.compile(r"(2И-\d+|\d{4}-\d{2}-\d{2}-\d+)", re.I)
_YEAR_IN_TEXT = re.compile(r"^\s*\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}")
# поля, которые перенос имеет право менять; всё остальное должно остаться как было
_MANAGED_FIELDS = set(appeals_mod.LEGACY_APPEAL_FIELDS) | {"appeals", appeals_mod.LEGACY_BACKUP_KEY}


def _ru(iso):
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}" if iso else ""


def _analyse(case):
    """(список обращений, замечания для ручной проверки)"""
    issues = []
    derived = appeals_mod.derive_from_legacy(case)
    raw_number = (case.get("court_ruling_number") or "").strip()
    raw_repeat = (case.get("repeat_ruling") or "").strip()
    if derived:
        a1 = derived[0]
        if raw_number and not a1["mgs_date"]:
            issues.append(f"№ определения «{raw_number}» — дата не распознана, впишите её вручную")
        elif raw_number and a1["mgs_number"] == raw_number and case.get("court_ruling_date"):
            issues.append(f"№ определения «{raw_number}» расходится с датой определения {_ru(case['court_ruling_date'])} — "
                          f"текст оставлен как есть, поправьте вручную")
        elif raw_number and not case.get("court_ruling_date") and not _YEAR_IN_TEXT.match(raw_number):
            issues.append(f"№ определения «{raw_number}» → дата {_ru(a1['mgs_date'])}, №{a1['mgs_number']} "
                          f"(год подставлен автоматически — проверьте)")
    if len(derived) > 1 and raw_repeat:
        a2 = derived[1]
        if a2["mgs_date"] and not _YEAR_IN_TEXT.match(raw_repeat):
            issues.append(f"«Повторное решение» «{raw_repeat}» → обращение №2: дата {_ru(a2['mgs_date'])}, "
                          f"№{a2['mgs_number']} (год подставлен автоматически — проверьте)")
        elif not a2["mgs_date"]:
            issues.append(f"«Повторное решение» «{raw_repeat}» перенесено в обращение №2 как номер МГС целиком — проверьте")
    if _NUMBER_IN_NOTES.search(case.get("notes") or ""):
        issues.append(f"в примечаниях похоже есть номер обращения: «{(case.get('notes') or '')[:80]}» — "
                      f"перенесите в нужное обращение (примечания не меняются)")
    return derived, issues


def _convert(rows):
    """Возвращает (новые строки, число перенесённых, замечания)."""
    out, changed, notes = [], 0, []
    for c in rows:
        c = copy.deepcopy(c)
        derived, issues = _analyse(c)
        if not isinstance(c.get("appeals"), list):
            backup = appeals_mod.legacy_backup(c)
            if backup is not None:
                c[appeals_mod.LEGACY_BACKUP_KEY] = backup
            c["appeals"] = derived
            c.update(appeals_mod.legacy_mirror(derived))
            changed += 1
            if issues:
                notes.append((c, issues))
        out.append(c)
    return out, changed, notes


def _verify(before, after, label):
    """Список найденных проблем (пустой — всё в порядке)."""
    problems = []
    if len(before) != len(after):
        problems.append(f"{label}: было {len(before)} записей, стало {len(after)}")
    before_by_id = {c.get("id"): c for c in before}
    after_by_id = {c.get("id"): c for c in after}
    if set(before_by_id) != set(after_by_id):
        problems.append(f"{label}: набор записей изменился")
    for cid, old in before_by_id.items():
        new = after_by_id.get(cid)
        if new is None:
            continue
        for k in set(old) | set(new):
            if k in _MANAGED_FIELDS:
                continue
            if old.get(k) != new.get(k):
                problems.append(f"{label} {cid}: изменилось поле «{k}»")
        if not isinstance(old.get("appeals"), list):
            backup = new.get(appeals_mod.LEGACY_BACKUP_KEY) or {}
            for f in appeals_mod.LEGACY_BACKUP_FIELDS:
                if (backup.get(f) or "") != (old.get(f) or ""):
                    problems.append(f"{label} {cid}: в резервной копии не совпадает «{f}»")
    return problems


def _backup_files(stamp):
    made = []
    for path in (storage.BLOCKING_CASES_FILE, storage.REPORT_ARCHIVE_FILE):
        if os.path.exists(path):
            dst = f"{path}.before-appeals-{stamp}"
            shutil.copy2(path, dst)
            made.append((path, dst))
    return made


def run(apply):
    active = storage.load_blocking_cases()
    archive = storage.load_report_archive()
    new_active, changed_a, notes_a = _convert(active)
    new_archive, changed_r, notes_r = _convert(archive)

    stuck = [c for c in new_active if c.get("needs_resend") and link_check.is_blocked(c)]

    print(f"Активных дел: {len(active)}, в архиве: {len(archive)}")
    print(f"{'Перенесено' if apply else 'Будет перенесено'} в новый формат обращений: "
          f"{changed_a} активных, {changed_r} архивных (остальные уже в новом формате)")
    all_notes = [("активные", c, i) for c, i in notes_a] + [("архив", c, i) for c, i in notes_r]
    if all_notes:
        print(f"\nПроверьте вручную ({len(all_notes)}) — данные НЕ потеряны, но разобраны с допущениями:")
        for source, c, issues in all_notes:
            print(f"  [{source}] «{c.get('author_name', '')}» — {c.get('url', '')}")
            for i in issues:
                print(f"      • {i}")
    if stuck:
        print(f"\nЗаблокированы, но висят с пометкой «ссылка снова доступна» ({len(stuck)}) —")
        print("откройте каждое и нажмите «Ложная тревога» или добавьте новое обращение:")
        for c in stuck:
            print(f"  «{c.get('author_name', '')}» — {c.get('url', '')}")

    if not apply:
        problems = _verify(active, new_active, "активные") + _verify(archive, new_archive, "архив")
        print("\nПробная проверка целостности: " + ("OK" if not problems else "ОШИБКИ:\n  " + "\n  ".join(problems)))
        print("Ничего не изменено. Запустите с --apply, чтобы записать.")
        return 0 if not problems else 1

    if not changed_a and not changed_r:
        print("\nПереносить нечего — файлы не изменены.")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backups = _backup_files(stamp)
    for src, dst in backups:
        print(f"Копия: {dst}")

    storage.save_blocking_cases(new_active)
    storage.save_report_archive(new_archive)

    # проверяем то, что реально легло на диск, а не то, что в памяти
    written_active = storage.load_blocking_cases()
    written_archive = storage.load_report_archive()
    problems = _verify(active, written_active, "активные") + _verify(archive, written_archive, "архив")
    if problems:
        for src, dst in backups:
            shutil.copy2(dst, src)
        print("\nПРОВЕРКА ЦЕЛОСТНОСТИ НЕ ПРОЙДЕНА — файлы возвращены из копий, ничего не изменено:")
        for p in problems[:50]:
            print(f"  {p}")
        return 1
    print("\nПроверка целостности после записи: OK — все дела на месте, остальные поля не изменились,")
    print(f"исходные значения сохранены в каждом деле в поле {appeals_mod.LEGACY_BACKUP_KEY}.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="записать изменения на диск")
    raise SystemExit(run(parser.parse_args().apply))


if __name__ == "__main__":
    main()
