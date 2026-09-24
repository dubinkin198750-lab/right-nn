"""Личные данные автора-истца (ФИО, паспорт, СНИЛС и т.п.) для заявлений
в суд — по тому же принципу, что и документы авторов (document_vault.py):

- Хранятся зашифрованными на диске (ключ — на сервере, защита от копирования
  файлов в обход приложения, не от доступа через само приложение).
- У администратора — полный прямой доступ: посмотреть, поправить, скопировать
  в любой момент.
- У обычного сотрудника — доступа напрямую нет вообще. Единственный способ
  как-то соприкоснуться с этими данными — через подготовку заявления в суд
  (petition.py), и каждое такое использование фиксируется в журнале действий.

Это НЕ те же данные, что личные данные самого сотрудника (тут вообще нет
такой сущности в системе) — это данные АВТОРА, то есть правообладателя,
от чьего имени подаётся заявление. У каждого автора — свои.
"""
import json
import os
import threading

from cryptography.fernet import Fernet

from . import storage

FIELDS = [
    "entity_type",  # "individual" (физлицо, по умолчанию) | "individual_entrepreneur" (ИП) | "organization" (юрлицо)
    # физическое лицо
    "full_name", "birth_date", "birth_place", "passport", "issued_by", "snils",
    # юридическое лицо / ИП — те же поля для обоих (свой ИНН есть у обоих),
    # разница только в заголовке раздела заявления (см. petition.py)
    "org_name", "org_inn", "org_kpp", "org_address", "org_representative",
    # договор и реквизиты для «Акта выполненных работ» — были на самом
    # объекте автора (authors.json), доступные через обычный PUT
    # /api/authors/<id> с проверкой роли admin прямо в эндпоинте; перенесены
    # сюда, в ту же зашифрованную запись, что и остальные чувствительные
    # данные автора, чтобы «Заказчик и реквизиты» показывала всё об одном
    # авторе из одного места, не из двух разных хранилищ.
    "customer_name", "customer_director", "contract_number", "contract_date", "monthly_fee",
]

_key_lock = threading.Lock()  # отдельная блокировка на создание файла ключа (см. document_vault.py)


def _store_file():
    # НЕ кешируем как константу модуля — вычисляем от текущего storage.DATA_DIR
    # при каждом обращении. Иначе подмена storage.DATA_DIR (например, в
    # тестах на изолированное хранилище) не подхватывается этим модулем,
    # и запись тихо уходит в настоящую data/ вместо временной папки теста —
    # именно та ошибка, ради которой был заведён общий _helpers.py.
    return os.path.join(storage.DATA_DIR, "author_personal_data.json")


def _key_file():
    return os.path.join(storage.DATA_DIR, ".author_personal_data_key")


def _load_or_create_key():
    with _key_lock:
        os.makedirs(storage.DATA_DIR, exist_ok=True)
        key_file = _key_file()
        if os.path.exists(key_file):
            with open(key_file, "rb") as f:
                return f.read().strip()
        key = Fernet.generate_key()
        with open(key_file, "wb") as f:
            f.write(key)
        return key


def _fernet():
    return Fernet(_load_or_create_key())


def _load_all():
    store_file = _store_file()
    with storage._lock:
        if not os.path.exists(store_file):
            return {}
        with open(store_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
    result = {}
    for author_id, ciphertext in raw.items():
        try:
            payload = _fernet().decrypt(ciphertext.encode("ascii"))
            result[author_id] = json.loads(payload.decode("utf-8"))
        except Exception:
            continue  # повреждённая или нечитаемая запись — пропускаем, не роняем всё приложение
    return result


def _save_one(author_id, fields):
    os.makedirs(storage.DATA_DIR, exist_ok=True)
    payload = json.dumps({k: fields.get(k, "") for k in FIELDS}, ensure_ascii=False).encode("utf-8")
    encrypted = _fernet().encrypt(payload).decode("ascii")
    store_file = _store_file()
    with storage._lock:
        all_raw = {}
        if os.path.exists(store_file):
            with open(store_file, "r", encoding="utf-8") as f:
                all_raw = json.load(f)
        all_raw[author_id] = encrypted
        with open(store_file, "w", encoding="utf-8") as f:
            json.dump(all_raw, f, ensure_ascii=False, indent=2)


def has_data(author_id):
    return author_id in _load_all()


def get(author_id):
    """Возвращает словарь полей или None, если для этого автора ничего не
    сохранено. Не проверяет права доступа — это забота вызывающего кода
    в app.py (роль admin для прямого доступа, либо внутреннее использование
    при подготовке заявления)."""
    return _load_all().get(author_id)


def save(author_id, fields):
    _save_one(author_id, fields)


def delete(author_id):
    store_file = _store_file()
    with storage._lock:
        if not os.path.exists(store_file):
            return
        with open(store_file, "r", encoding="utf-8") as f:
            all_raw = json.load(f)
        if author_id in all_raw:
            del all_raw[author_id]
            with open(store_file, "w", encoding="utf-8") as f:
                json.dump(all_raw, f, ensure_ascii=False, indent=2)
