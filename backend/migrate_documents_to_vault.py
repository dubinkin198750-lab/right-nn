"""Разовая миграция: шифрует документы авторов, загруженные ДО того, как
появилось зашифрованное хранилище (document_vault.py).

Запускать один раз после обновления кода на сервере:

    python -m backend.migrate_documents_to_vault

Безопасно запускать повторно — уже зашифрованные файлы просто
пропускаются. Ничего не меняет в metadata (documents.json), только
переносит содержимое файлов из старой открытой папки data/documents в
новое зашифрованное хранилище data/documents_vault и удаляет исходники
после успешного переноса.
"""
import os

from . import document_vault, storage


def run():
    docs = storage.load_documents()
    migrated = 0
    already_ok = 0
    missing = 0

    for doc in docs:
        stored_filename = doc.get("stored_filename")
        if not stored_filename:
            continue

        vault_path = os.path.join(document_vault._vault_dir(), stored_filename)
        if os.path.exists(vault_path):
            already_ok += 1
            continue

        old_path = os.path.join(storage.DOCUMENTS_DIR, stored_filename)
        if not os.path.exists(old_path):
            print(f"  пропущен (файл не найден нигде): {doc.get('original_name', stored_filename)}")
            missing += 1
            continue

        with open(old_path, "rb") as f:
            raw = f.read()
        document_vault.save_encrypted(stored_filename, raw)
        os.remove(old_path)
        migrated += 1
        print(f"  зашифрован: {doc.get('original_name', stored_filename)}")

    print()
    print(f"Готово. Перенесено: {migrated}. Уже были зашифрованы: {already_ok}. Не найдено: {missing}.")


if __name__ == "__main__":
    run()
