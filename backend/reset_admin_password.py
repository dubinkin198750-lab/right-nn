"""Восстановление доступа администратора — на случай, если единственный
admin забыл пароль, уволился без передачи доступа, или ошибся при смене
пароля.

Требует доступа к файловой системе сервера — то же доверие, что уже
принято для остальных management-скриптов этого проекта (например,
migrate_documents_to_vault.py). Это осознанный компромисс: без такого
«аварийного люка» единственный admin был бы единой точкой отказа для
всей организации, а более сложный механизм (email-восстановление,
секретные вопросы) для инструмента на несколько сотрудников — избыточен
и добавляет собственные риски.

ВАЖНО: сброс пароля НЕ восстанавливает доступ к зашифрованным личным
данным авторов и документам — эти хранилища (author_personal_data.json,
documents_vault/) защищены отдельными ключами на диске (см. заметки к
развёртыванию), не паролем admin. Смена пароля не теряет доступ к ним,
но и не является для них ключом — тут можно быть спокойным: сброс пароля
не «ломает» шифрование, оно продолжит работать как прежде.

Запускать на сервере:

    python -m backend.reset_admin_password ИМЯ_ПОЛЬЗОВАТЕЛЯ

Если пользователя с таким именем и ролью admin не существует — скрипт
покажет текущих администраторов (включая заданных через .env/APP_USERS)
и подскажет дальнейшие шаги, включая создание нового администратора,
если во всей системе не осталось ни одного.
"""
import argparse
import getpass
import sys

from . import auth, storage


def _create_new_admin(username):
    password = getpass.getpass("Пароль для нового администратора: ")
    password2 = getpass.getpass("Повторите пароль: ")
    if password != password2:
        print("Пароли не совпадают, ничего не создано.")
        return 1
    if len(password) < 8:
        print("Пароль слишком короткий (меньше 8 символов) — ничего не создано.")
        return 1
    try:
        storage.create_user(username, auth.hash_password(password), "admin")
    except ValueError as e:
        print(f"Не удалось создать: {e}")
        return 1
    print(f"Создан новый администратор «{username}». Войдите с этим именем и паролем.")
    return 0


def run(argv=None):
    parser = argparse.ArgumentParser(description="Сбросить пароль администратора или создать нового, если не осталось ни одного")
    parser.add_argument("username", help="Имя пользователя-администратора (из users.json)")
    parser.add_argument("--create", action="store_true", help="Создать нового администратора с этим именем (только если в системе нет ни одного)")
    args = parser.parse_args(argv)

    user = next((u for u in storage.load_users() if u["username"] == args.username), None)
    env_admins = auth.env_admin_usernames()

    if args.create:
        existing_admins = [u["username"] for u in storage.load_users() if u["role"] == "admin"]
        if existing_admins or env_admins:
            print("В системе уже есть администратор — по правилам этого приложения admin должен быть только один.")
            print("Существующие:", ", ".join(existing_admins + env_admins) or "—")
            print("Если это учётная запись, до которой действительно больше никто не может достучаться —")
            print("сначала удалите её вручную из data/users.json (или уберите из APP_USERS в .env),")
            print("затем повторите эту команду.")
            return 1
        return _create_new_admin(args.username)

    if not user:
        print(f"Пользователь «{args.username}» не найден в users.json.")
        admins = [u["username"] for u in storage.load_users() if u["role"] == "admin"]
        if admins:
            print("Текущие администраторы в users.json:", ", ".join(admins))
        if env_admins:
            print(
                "Есть также администраторы через .env (APP_USERS):", ", ".join(env_admins),
                "— их пароль меняется прямо в .env на сервере, этот скрипт их не касается.",
            )
        if not admins and not env_admins:
            print("Администраторов не найдено вообще ни одним способом.")
            print(f"Чтобы создать нового администратора с именем «{args.username}», запустите:")
            print(f"    python -m backend.reset_admin_password {args.username} --create")
        return 1

    if user["role"] != "admin":
        print(f"Пользователь «{args.username}» существует, но его роль — {user['role']}, не admin.")
        print("Этот скрипт меняет пароль только у существующего admin, не назначает роль.")
        return 1

    password = getpass.getpass("Новый пароль: ")
    password2 = getpass.getpass("Повторите новый пароль: ")
    if password != password2:
        print("Пароли не совпадают, ничего не изменено.")
        return 1
    if len(password) < 8:
        print("Пароль слишком короткий (меньше 8 символов) — не изменено.")
        return 1

    storage.update_user_password(user["id"], auth.hash_password(password))
    print(f"Пароль пользователя «{args.username}» обновлён.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
