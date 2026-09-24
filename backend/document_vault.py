"""Шифрование документов авторов (доверенности, договоры, выписки и т.п.)
«при хранении» — отдельная зашифрованная папка на диске, отличная от
обычной data/documents.

Важное отличие от личных данных сотрудника (personal_data.py): у авторов
нет своего пароля входа в систему — они просто карточки в базе, а не
пользователи. Поэтому ключ шифрования здесь не привязан к чьему-то
паролю, а хранится на самом сервере (тот же принцип, что уже используется
для SECRET_KEY сессий Flask — см. data/.secret_key в app.py): один раз
создаётся, дальше просто используется приложением.

Это защищает документы от одного конкретного риска — «кто-то скопировал
файлы с диска или из бэкапа напрямую, в обход приложения» — такой человек
получит нечитаемые байты без этого ключевого файла. Это НЕ защита от
доступа через само приложение: кто должен иметь право открывать документы
через приложение — решается на уровне ролей в app.py (в первую очередь —
доступ только у admin, обычный сотрудник получает документы только
опосредованно, в момент подготовки заявления в суд, с записью в журнал
действий, какой документ для чего использовался).
"""
import os
import threading

from cryptography.fernet import Fernet

# Вычисляем путь к data/ независимо от storage.py (не импортируем storage
# отсюда специально) — иначе при обратном импорте document_vault из
# storage.py (для каскадного удаления файлов при удалении автора)
# получился бы циклический импорт между модулями. По той же причине здесь
# своя собственная блокировка, а не storage._lock.
#
# DATA_DIR — единственная точка настройки, и это обычная переменная
# модуля (не «застывшая» в других путях константа) специально для того,
# чтобы тесты могли подменить её на временную папку простым присваиванием
# document_vault.DATA_DIR = tmp — и это подхватится всеми функциями ниже,
# а не только теми, что читают DATA_DIR при импорте.
_lock = threading.Lock()

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _vault_dir():
    return os.path.join(DATA_DIR, "documents_vault")


def _vault_key_file():
    return os.path.join(DATA_DIR, ".documents_vault_key")


def _load_or_create_key():
    # Самое опасное место без блокировки: если два потока ОДНОВРЕМЕННО не
    # находят файл ключа и оба генерируют свой — тот, что запишется вторым,
    # «победит», а всё, что уже успело зашифроваться первым ключом (в этом
    # же самом всплеске параллельных запросов), станет нечитаемым.
    with _lock:
        os.makedirs(DATA_DIR, exist_ok=True)
        key_file = _vault_key_file()
        if os.path.exists(key_file):
            with open(key_file, "rb") as f:
                return f.read().strip()
        key = Fernet.generate_key()
        with open(key_file, "wb") as f:
            f.write(key)
        return key


def _fernet():
    return Fernet(_load_or_create_key())


def save_encrypted(stored_filename, raw_bytes):
    vault_dir = _vault_dir()
    os.makedirs(vault_dir, exist_ok=True)
    encrypted = _fernet().encrypt(raw_bytes)
    path = os.path.join(vault_dir, stored_filename)
    with _lock:
        with open(path, "wb") as f:
            f.write(encrypted)
    return len(raw_bytes)  # исходный размер файла — для отображения в интерфейсе


def read_decrypted(stored_filename):
    path = os.path.join(_vault_dir(), stored_filename)
    with _lock:
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            encrypted = f.read()
    return _fernet().decrypt(encrypted)


def delete_encrypted(stored_filename):
    path = os.path.join(_vault_dir(), stored_filename)
    with _lock:
        if os.path.exists(path):
            os.remove(path)


def migrate_plaintext_folder(plaintext_dir):
    """Разовая миграция: шифрует всё, что лежит в старой незашифрованной
    папке (data/documents), и удаляет исходники после успешного шифрования.
    Не трогает файлы, которых нет в metadata (documents.json) — это забота
    вызывающего кода, здесь только берём список путей на входе.
    Возвращает список перенесённых имён файлов."""
    migrated = []
    if not os.path.isdir(plaintext_dir):
        return migrated
    for filename in os.listdir(plaintext_dir):
        src = os.path.join(plaintext_dir, filename)
        if not os.path.isfile(src):
            continue
        with open(src, "rb") as f:
            raw = f.read()
        save_encrypted(filename, raw)
        os.remove(src)
        migrated.append(filename)
    return migrated
