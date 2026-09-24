"""Аутентификация: роли доступа + два источника пользователей.

1. Динамические пользователи (data/users.json, пароли хешированы) — создаются
   через bootstrap (первый администратор) или по ссылке-приглашению. Это
   основной, рекомендуемый способ.
2. Старый способ через .env (APP_USERS=имя:пароль,...) — оставлен для
   обратной совместимости с уже развёрнутыми установками; такие пользователи
   всегда получают роль admin, пароли у них по-прежнему открытым текстом
   в .env (как и раньше — ничего не мигрируем автоматически, чтобы не менять
   поведение существующих установок без спроса).

Роли: admin (всё, включая управление доступом и общими настройками),
editor (работа с авторами/произведениями/делами блокировки/документами,
без управления пользователями/блок-листом/справочником сайтов),
viewer (только просмотр — GET-запросы).

is_enabled() == True, если есть хотя бы один способ войти (через .env ИЛИ
через созданных пользователей). Пока ни того, ни другого нет — приложение
работает без входа, как раньше (сознательный выбор: обновление никого не
блокирует неожиданно).
"""
import hmac
import os

from werkzeug.security import check_password_hash, generate_password_hash

from . import storage

ROLES = ["admin", "editor", "viewer"]
ROLE_RANK = {"viewer": 0, "editor": 1, "admin": 2}


def _parse_env_users():
    raw = os.environ.get("APP_USERS", "").strip()
    if not raw:
        return {}
    users = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        username, password = pair.split(":", 1)
        username = username.strip()
        password = password.strip()
        if username and password:
            users[username] = password
    return users


def is_enabled():
    return bool(_parse_env_users()) or bool(storage.load_users())


def env_admin_count():
    """Сколько admin-аккаунтов задано через APP_USERS в .env — все они
    всегда получают роль admin (см. докстринг модуля). Нужно учитывать
    это число при проверке «admin должен быть только один», иначе правило
    можно тихо обойти через .env, пока динамический пользователь
    проверяется только по users.json."""
    return len(_parse_env_users())


def env_admin_usernames():
    """Имена пользователей, заданных через APP_USERS — для интерфейсов
    восстановления доступа (reset_admin_password.py), где важно не просто
    число, а конкретные имена, которые видит человек на экране."""
    return list(_parse_env_users().keys())


def check_login(username, password):
    """Возвращает роль при успешном входе, иначе None. Проверяет сначала
    .env-пользователей (всегда роль admin), потом динамических (users.json)."""
    env_users = _parse_env_users()
    expected = env_users.get(username)
    if expected is not None:
        # сравниваем байты, а не str — hmac.compare_digest не поддерживает
        # строки с не-ASCII символами (а пароль вполне может быть кириллицей)
        if hmac.compare_digest(expected.encode("utf-8"), password.encode("utf-8")):
            return "admin"
        return None

    user = storage.get_user_by_username(username)
    if user is None:
        # фиктивная проверка фиксированной длины, чтобы не палить таймингом
        # сам факт существования пользователя
        generate_password_hash("x")
        return None
    if check_password_hash(user["password_hash"], password):
        return user["role"]
    return None


def hash_password(password):
    return generate_password_hash(password)


def has_role_at_least(role, minimum):
    return ROLE_RANK.get(role, -1) >= ROLE_RANK.get(minimum, 99)


def list_usernames():
    names = sorted(_parse_env_users().keys())
    names += [u["username"] for u in storage.load_users()]
    return sorted(set(names))
