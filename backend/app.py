import base64
import io
import os
import re
import secrets
import threading
import time
import uuid
import zipfile
from calendar import monthrange
from datetime import datetime
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, request, send_from_directory, Response, send_file, session, redirect  # noqa: E402
from werkzeug.utils import secure_filename  # noqa: E402

from . import storage, jobs, yandex_search, search_sources, site_search, exporters, reports, auth, netinfo, document_vault, author_personal_data, petition, link_check, image_stamp, screenshot_capture, analytics, duckduckgo_search, chronic_links  # noqa: E402
from . import appeals as appeals_mod  # noqa: E402
from . import vk_search, torznab_search  # noqa: E402

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

# Секретный ключ для подписи сессионных cookie. Если не задан в .env —
# генерируем один раз и сохраняем в data/.secret_key, чтобы сессии не
# слетали при каждом перезапуске сервера (иначе всех разлогинивало бы).
_secret_key_env = os.environ.get("SECRET_KEY", "").strip()
if _secret_key_env:
    app.secret_key = _secret_key_env
else:
    _key_path = os.path.join(storage.DATA_DIR, ".secret_key")
    os.makedirs(storage.DATA_DIR, exist_ok=True)
    if os.path.exists(_key_path):
        with open(_key_path, "r", encoding="utf-8") as f:
            app.secret_key = f.read().strip()
    else:
        app.secret_key = secrets.token_hex(32)
        with open(_key_path, "w", encoding="utf-8") as f:
            f.write(app.secret_key)

DEFAULT_SOURCES = {"yandex": True, "google": False, "duckduckgo": False, "avito": False, "telegram": False,
                   "vk": False, "vk_video": False, "torrents": False}


# ---------- аутентификация: роли + вход по паролю или по ссылке-приглашению ----------
AUTH_PAGE_STYLE = """
<style>
  body { font-family: system-ui, sans-serif; background: #F6F4F1; display: flex;
         align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }
  .box { background: #fff; padding: 32px 36px; border-radius: 14px; box-shadow: 0 10px 40px rgba(15,33,66,0.15); width: 320px; }
  h1 { font-size: 18px; color: #0F2142; margin: 0 0 10px; }
  p.hint { font-size: 12.5px; color: #6B7178; margin: 0 0 18px; }
  label { display: block; font-size: 12.5px; font-weight: 600; color: #6B7178; margin-bottom: 14px; }
  input { width: 100%; margin-top: 6px; padding: 9px 11px; border-radius: 8px; border: 1px solid #E4E0DA;
          font-size: 14px; box-sizing: border-box; }
  button { width: 100%; padding: 10px; border-radius: 8px; border: none; background: #B08D57;
           color: #0F2142; font-weight: 700; font-size: 14px; cursor: pointer; }
  .error { color: #B4443A; font-size: 13px; margin-bottom: 14px; }
</style>"""

LOGIN_PAGE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>Вход — Мониторинг ИС</title>""" + AUTH_PAGE_STYLE + """</head>
<body>
  <form class="box" method="post" action="/login">
    <h1>Мониторинг ИС — вход</h1>
    __ERROR_HTML__
    <label>Имя пользователя<input type="text" name="username" autofocus required></label>
    <label>Пароль<input type="password" name="password" required></label>
    <button type="submit">Войти</button>
  </form>
</body></html>"""

JOIN_PAGE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>Присоединиться — Мониторинг ИС</title>""" + AUTH_PAGE_STYLE + """</head>
<body>
  <form class="box" method="post" action="/join">
    <h1>Создать доступ</h1>
    <p class="hint">Вас пригласили с ролью «__ROLE__». Придумайте себе имя пользователя и пароль.</p>
    __ERROR_HTML__
    <input type="hidden" name="token" value="__TOKEN__">
    <label>Имя пользователя<input type="text" name="username" autofocus required></label>
    <label>Пароль (минимум 8 символов)<input type="password" name="password" required minlength="8"></label>
    <button type="submit">Создать и войти</button>
  </form>
</body></html>"""

BOOTSTRAP_PAGE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>Первичная настройка — Мониторинг ИС</title>""" + AUTH_PAGE_STYLE + """</head>
<body>
  <form class="box" method="post" action="/setup">
    <h1>Включить вход по паролю</h1>
    <p class="hint">Вы создаёте первого администратора. После этого вход станет обязательным для всех.</p>
    __ERROR_HTML__
    <label>Имя пользователя<input type="text" name="username" autofocus required></label>
    <label>Пароль (минимум 8 символов)<input type="password" name="password" required minlength="8"></label>
    <button type="submit">Создать администратора</button>
  </form>
</body></html>"""

ROLE_LABELS_RU = {"admin": "администратор", "editor": "редактор", "viewer": "только просмотр"}


@app.before_request
def require_login():
    if request.path in ("/login", "/logout", "/join", "/setup") or request.path.startswith("/api/auth/"):
        return
    if not auth.is_enabled():
        return  # аутентификация не настроена — работаем как раньше, без логина
    if session.get("username"):
        return
    if request.path.startswith("/api/"):
        return jsonify({"error": "Не авторизован"}), 401
    return redirect("/login")


def require_role(minimum):
    """Декоратор: доступ только для сессии с ролью не ниже `minimum`.
    Если аутентификация вообще выключена — пропускает всех (как и раньше)."""
    def decorator(fn):
        import functools

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not auth.is_enabled():
                return fn(*args, **kwargs)
            role = session.get("role")
            if not auth.has_role_at_least(role, minimum):
                return jsonify({"error": f"Недостаточно прав (нужна роль не ниже «{ROLE_LABELS_RU.get(minimum, minimum)}»)"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


@app.route("/login", methods=["GET", "POST"])
def login():
    if not auth.is_enabled():
        return redirect("/")
    if request.method == "GET":
        return LOGIN_PAGE.replace("__ERROR_HTML__", "")
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    role = auth.check_login(username, password)
    if role:
        session["username"] = username
        session["role"] = role
        return redirect("/")
    error_div = '<div class="error">Неверное имя пользователя или пароль</div>'
    return LOGIN_PAGE.replace("__ERROR_HTML__", error_div), 401


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("username", None)
    session.pop("role", None)
    return redirect("/login")


@app.route("/setup", methods=["GET", "POST"])
def setup():
    """Первичная настройка: создать первого администратора. Работает, только
    пока вообще ни одного способа входа не настроено — после этого маршрут
    сам себя закрывает (чтобы нельзя было завести второго «первого» админа в обход приглашений)."""
    if auth.is_enabled():
        return redirect("/login")
    if request.method == "GET":
        return BOOTSTRAP_PAGE.replace("__ERROR_HTML__", "")
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    if not username or len(password) < 8:
        return BOOTSTRAP_PAGE.replace("__ERROR_HTML__", '<div class="error">Укажите имя и пароль не короче 8 символов</div>'), 400
    user = storage.create_user(username, auth.hash_password(password), "admin", created_by=None)
    session["username"] = user["username"]
    session["role"] = "admin"
    storage.log_action(username, "включил вход по паролю", "создан первый администратор")
    return redirect("/")


@app.route("/join", methods=["GET", "POST"])
def join():
    token = request.args.get("token") if request.method == "GET" else request.form.get("token")
    invite = storage.get_invite(token) if token else None
    if not storage.is_invite_valid(invite):
        return "Ссылка-приглашение недействительна, уже использована или её срок истёк.", 410

    if request.method == "GET":
        page = JOIN_PAGE.replace("__ROLE__", ROLE_LABELS_RU.get(invite["role"], invite["role"]))
        page = page.replace("__TOKEN__", token).replace("__ERROR_HTML__", "")
        return page

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    if not username or len(password) < 8:
        page = JOIN_PAGE.replace("__ROLE__", ROLE_LABELS_RU.get(invite["role"], invite["role"]))
        page = page.replace("__TOKEN__", token)
        page = page.replace("__ERROR_HTML__", '<div class="error">Укажите имя и пароль не короче 8 символов</div>')
        return page, 400
    try:
        user = storage.create_user(username, auth.hash_password(password), invite["role"], created_by=invite.get("created_by"))
    except ValueError as e:
        page = JOIN_PAGE.replace("__ROLE__", ROLE_LABELS_RU.get(invite["role"], invite["role"]))
        page = page.replace("__TOKEN__", token)
        page = page.replace("__ERROR_HTML__", f'<div class="error">{e}</div>')
        return page, 400

    storage.mark_invite_used(token, username)
    session["username"] = user["username"]
    session["role"] = user["role"]
    storage.log_action(username, "принял приглашение", f"роль: {invite['role']}")
    return redirect("/")


@app.get("/api/auth/whoami")
def whoami():
    return jsonify({
        "enabled": auth.is_enabled(),
        "username": session.get("username"),
        "role": session.get("role"),
    })


# ---------- управление доступом (только admin) ----------
@app.get("/api/users")
@require_role("admin")
def list_users():
    users = storage.load_users()
    return jsonify([{k: v for k, v in u.items() if k != "password_hash"} for u in users])


@app.put("/api/users/<user_id>")
@require_role("admin")
def change_user_role(user_id):
    data = request.get_json(force=True)
    role = data.get("role")
    if role not in auth.ROLES:
        return jsonify({"error": f"Недопустимая роль. Разрешены: {auth.ROLES}"}), 400
    target = storage.get_user_by_id(user_id)
    if not target:
        return jsonify({"error": "Пользователь не найден"}), 404
    if target["role"] == "admin" and role != "admin" and _total_admin_count() <= 1:
        return jsonify({"error": "Нельзя понизить последнего администратора — сначала назначьте другого"}), 400
    if role == "admin" and target["role"] != "admin" and _total_admin_count() >= 1:
        return jsonify({"error": "В системе уже есть администратор — по правилам этого приложения admin должен быть только один"}), 400
    updated = storage.update_user_role(user_id, role)
    _log("изменил роль пользователя", f"{target['username']}: {target['role']} -> {role}")
    return jsonify({k: v for k, v in updated.items() if k != "password_hash"})


@app.delete("/api/users/<user_id>")
@require_role("admin")
def remove_user(user_id):
    target = storage.get_user_by_id(user_id)
    if not target:
        return jsonify({"error": "Пользователь не найден"}), 404
    if target["role"] == "admin" and _total_admin_count() <= 1:
        return jsonify({"error": "Нельзя удалить последнего администратора"}), 400
    if target["username"] == session.get("username"):
        return jsonify({"error": "Нельзя удалить самого себя, пока вы вошли под этим пользователем"}), 400
    storage.delete_user(user_id)
    _log("удалил пользователя", target["username"])
    return jsonify({"ok": True})


@app.get("/api/invites")
@require_role("admin")
def list_invites():
    invites = [i for i in storage.load_invites() if storage.is_invite_valid(i)]
    return jsonify(invites)


@app.post("/api/invites")
@require_role("admin")
def create_invite():
    data = request.get_json(force=True)
    role = data.get("role")
    if role not in auth.ROLES:
        return jsonify({"error": f"Недопустимая роль. Разрешены: {auth.ROLES}"}), 400
    if role == "admin" and _total_admin_count() >= 1:
        return jsonify({"error": "В системе уже есть администратор — по правилам этого приложения admin должен быть только один"}), 400
    invite = storage.create_invite(role, created_by=session.get("username"))
    _log("создал ссылку-приглашение", f"роль: {role}")
    return jsonify({**invite, "join_url": f"/join?token={invite['token']}"}), 201


@app.delete("/api/invites/<token>")
@require_role("admin")
def revoke_invite(token):
    storage.delete_invite(token)
    _log("отозвал ссылку-приглашение", token[:8] + "…")
    return jsonify({"ok": True})


# ---------- временные разрешения на просмотр документов автора (только admin выдаёт/отзывает) ----------
@app.get("/api/document-access-grants")
@require_role("admin")
def list_document_access_grants():
    """Все разрешения (и активные, и истёкшие/отозванные — фронтенд сам
    решает, что показывать по умолчанию, полезно для истории)."""
    grants = storage.load_document_access_grants()
    authors_by_id = {a["id"]: a["name"] for a in storage.load_authors()}
    for g in grants:
        g["author_name"] = authors_by_id.get(g["author_id"]) if g["author_id"] else None
    return jsonify(grants)


@app.get("/api/document-access-grants/mine")
def my_document_access_grants():
    """Для самого сотрудника — какие иконки документов/личных данных ему
    сейчас показывать в дереве авторов (см. renderTree во frontend)."""
    username, err = _require_login_username()
    if err:
        return err
    return jsonify(storage.list_active_grants_for_username(username))


@app.post("/api/document-access-grants")
@require_role("admin")
def create_document_access_grant():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    scope = data.get("scope")
    author_id = data.get("author_id")
    duration_days = data.get("duration_days")
    expires_at_raw = data.get("expires_at")  # ISO-дата, альтернатива duration_days

    if not username or not any(u["username"] == username for u in storage.load_users()):
        return jsonify({"error": "Не найден такой сотрудник"}), 400
    if scope not in ("all", "author"):
        return jsonify({"error": "scope должен быть 'all' или 'author'"}), 400
    if scope == "author":
        if not author_id or not storage.get_author(author_id):
            return jsonify({"error": "Для scope='author' нужен существующий author_id"}), 400
    else:
        author_id = None

    if duration_days:
        try:
            duration_days = float(duration_days)
        except (TypeError, ValueError):
            return jsonify({"error": "duration_days должно быть числом"}), 400
        if duration_days <= 0:
            return jsonify({"error": "duration_days должно быть положительным"}), 400
        expires_at = time.time() + duration_days * 86400
    elif expires_at_raw:
        try:
            expires_at = datetime.fromisoformat(expires_at_raw).timestamp()
        except ValueError:
            return jsonify({"error": "expires_at должен быть в формате ISO (YYYY-MM-DD или YYYY-MM-DDTHH:MM)"}), 400
    else:
        return jsonify({"error": "Укажите либо duration_days, либо expires_at"}), 400

    if expires_at <= time.time():
        return jsonify({"error": "Дата окончания должна быть в будущем"}), 400

    grant = storage.create_document_access_grant(
        username=username, scope=scope, author_id=author_id,
        granted_by=session.get("username"), expires_at=expires_at,
    )
    scope_desc = "все авторы" if scope == "all" else (storage.get_author(author_id) or {}).get("name", author_id)
    _log("выдал временное разрешение на документы", f"{username} — {scope_desc}, до {datetime.fromtimestamp(expires_at).strftime('%d.%m.%Y %H:%M')}")
    return jsonify(grant), 201


@app.delete("/api/document-access-grants/<grant_id>")
@require_role("admin")
def revoke_document_access_grant(grant_id):
    grant = storage.revoke_document_access_grant(grant_id)
    if not grant:
        return jsonify({"error": "Разрешение не найдено"}), 404
    _log("отозвал временное разрешение на документы", f"{grant['username']}")
    return jsonify({"ok": True})


# ---------- временные разрешения на редактирование справочника «Поиск по
# сайтам» (только admin выдаёт/отзывает) ----------
@app.get("/api/site-access-grants")
@require_role("admin")
def list_site_access_grants():
    return jsonify(storage.load_site_access_grants())


@app.get("/api/site-access-grants/mine")
def my_site_access_grant():
    """Есть ли у текущего сотрудника сейчас право редактировать справочник
    сайтов — для фронтенда, показывать ли кнопки «Изменить»/«Удалить»/
    «+Добавить сайт» (см. renderTree и site-search view во frontend)."""
    username, err = _require_login_username()
    if err:
        return err
    return jsonify({"has_access": storage.has_active_site_access_grant(username)})


@app.post("/api/site-access-grants")
@require_role("admin")
def create_site_access_grant():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    duration_days = data.get("duration_days")
    expires_at_raw = data.get("expires_at")

    if not username or not any(u["username"] == username for u in storage.load_users()):
        return jsonify({"error": "Не найден такой сотрудник"}), 400

    if duration_days:
        try:
            duration_days = float(duration_days)
        except (TypeError, ValueError):
            return jsonify({"error": "duration_days должно быть числом"}), 400
        if duration_days <= 0:
            return jsonify({"error": "duration_days должно быть положительным"}), 400
        expires_at = time.time() + duration_days * 86400
    elif expires_at_raw:
        try:
            expires_at = datetime.fromisoformat(expires_at_raw).timestamp()
        except ValueError:
            return jsonify({"error": "expires_at должен быть в формате ISO (YYYY-MM-DD или YYYY-MM-DDTHH:MM)"}), 400
    else:
        return jsonify({"error": "Укажите либо duration_days, либо expires_at"}), 400

    if expires_at <= time.time():
        return jsonify({"error": "Дата окончания должна быть в будущем"}), 400

    grant = storage.create_site_access_grant(username=username, granted_by=session.get("username"), expires_at=expires_at)
    _log("выдал временное разрешение на справочник сайтов", f"{username} — до {datetime.fromtimestamp(expires_at).strftime('%d.%m.%Y %H:%M')}")
    return jsonify(grant), 201


@app.delete("/api/site-access-grants/<grant_id>")
@require_role("admin")
def revoke_site_access_grant(grant_id):
    grant = storage.revoke_site_access_grant(grant_id)
    if not grant:
        return jsonify({"error": "Разрешение не найдено"}), 404
    _log("отозвал временное разрешение на справочник сайтов", f"{grant['username']}")
    return jsonify({"ok": True})


def _require_site_edit_access():
    """admin — всегда можно; редактор — только если ему явно выдано
    временное разрешение (см. /api/site-access-grants выше)."""
    if not auth.is_enabled():
        return True
    role = session.get("role")
    if auth.has_role_at_least(role, "admin"):
        return True
    username = session.get("username")
    return bool(username and storage.has_active_site_access_grant(username))


def require_site_edit_access(fn):
    """Декоратор — как require_role, но проверка комбинированная (admin
    ИЛИ активное разрешение), а не просто сравнение уровня роли. Отдельный
    декоратор, а не ручной вызов внутри каждого маршрута — так его нельзя
    случайно забыть на новом эндпоинте (см. заметку разработки, 03.09 —
    именно так и было раньше, риск был реальный)."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not _require_site_edit_access():
            return jsonify({"error": "Недостаточно прав — нужна роль admin либо временное разрешение на редактирование справочника сайтов"}), 403
        return fn(*args, **kwargs)
    return wrapper


def _log(action, details=""):
    storage.log_action(session.get("username"), action, details)


def _total_admin_count():
    """Учитывает и динамических admin (users.json), и admin через .env
    (APP_USERS — там все пользователи всегда admin) — иначе правило
    «admin должен быть только один» можно тихо обойти через .env, пока
    проверяется только users.json."""
    return storage.count_admins() + auth.env_admin_count()


# ---------- frontend ----------
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


# ---------- settings ----------
@app.get("/api/settings")
def get_settings():
    return jsonify({
        "yandex_configured": yandex_search.is_configured(),
        "google_configured": search_sources.is_google_configured(),
        "telegram_configured": exporters.telegram_is_configured(),
        "demo_mode": not yandex_search.is_configured(),
        "duckduckgo_serpapi_fallback_configured": duckduckgo_search.is_serpapi_fallback_configured(),
        "vk_configured": vk_search.is_configured(),
        "vk_video_configured": vk_search.is_video_configured(),
        "torrents_configured": torznab_search.is_configured(),
        "yandex_response_format": yandex_search.response_format_mode(),
        "google_demo_blocked": not search_sources.source_available("google")[0],
    })


# ---------- authors ----------

@app.get("/api/authors")
def list_authors():
    authors = storage.load_authors()
    works = storage.load_works()
    for a in authors:
        a["works_count"] = sum(1 for w in works if w["author_id"] == a["id"])
    return jsonify(authors)


@app.post("/api/authors")
@require_role("editor")
def create_author():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Укажите имя автора"}), 400
    author = {"id": None, "name": name}
    start_day = data.get("report_period_start_day")
    if start_day is not None:
        try:
            start_day = int(start_day)
        except (TypeError, ValueError):
            return jsonify({"error": "День начала отчётного периода должен быть числом"}), 400
        if not (1 <= start_day <= 28):
            return jsonify({"error": "День начала отчётного периода — от 1 до 28"}), 400
        author["report_period_start_day"] = start_day
    saved = storage.upsert_author(author)
    _log("создал автора", name)
    return jsonify(saved), 201


@app.put("/api/authors/<author_id>")
@require_role("editor")
def update_author(author_id):
    """Переименование + день начала отчётного периода (см. заметку
    разработки — у каждого автора он может быть свой, не 1-е число
    месяца по умолчанию). Реквизиты заказчика/договора остаются в
    защищённой записи author_personal_data (только admin, см.
    /api/authors/<id>/personal-data и раздел «Заказчик и реквизиты»),
    сюда не относятся."""
    existing = storage.get_author(author_id)
    if not existing:
        return jsonify({"error": "Автор не найден"}), 404
    old_name = existing["name"]
    data = request.get_json(force=True)
    existing["name"] = (data.get("name") or existing["name"]).strip()
    if "report_period_start_day" in data:
        start_day = data.get("report_period_start_day")
        try:
            start_day = int(start_day)
        except (TypeError, ValueError):
            return jsonify({"error": "День начала отчётного периода должен быть числом"}), 400
        if not (1 <= start_day <= 28):
            return jsonify({"error": "День начала отчётного периода — от 1 до 28"}), 400
        existing["report_period_start_day"] = start_day
    storage.upsert_author(existing)
    _log("обновил автора", f"{old_name} -> {existing['name']}")
    return jsonify(existing)


@app.delete("/api/authors/<author_id>")
@require_role("editor")
def remove_author(author_id):
    existing = storage.get_author(author_id)
    storage.delete_author(author_id)  # каскадно удалит и произведения, и документы
    _log("удалил автора", existing["name"] if existing else author_id)
    return jsonify({"ok": True})


# ---------- документы автора (доверенности, подтверждение авторства и т.п.) ----------
ALLOWED_DOC_EXTENSIONS = {
    "pdf", "doc", "docx", "odt", "rtf",
    "jpg", "jpeg", "png", "tif", "tiff", "heic",
    "sig", "p7s", "sgn",           # форматы электронной подписи
    "zip", "rar", "7z",             # архивы — доверенность часто идёт архивом с файлом подписи внутри
}
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 МБ на файл


@app.get("/api/authors/<author_id>/documents")
def list_author_documents(author_id):
    if not storage.get_author(author_id):
        return jsonify({"error": "Автор не найден"}), 404
    if not _can_view_author_sensitive(author_id):
        return jsonify({"error": "Недостаточно прав — нужна роль admin или временное разрешение на просмотр"}), 403
    return jsonify(storage.get_author_documents(author_id))


@app.post("/api/authors/<author_id>/documents")
@require_role("admin")
def upload_author_document(author_id):
    if not storage.get_author(author_id):
        return jsonify({"error": "Автор не найден"}), 404
    if "file" not in request.files:
        return jsonify({"error": "Файл не передан"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Файл не выбран"}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_DOC_EXTENSIONS:
        return jsonify({"error": f"Недопустимый тип файла .{ext}. Разрешены: {', '.join(sorted(ALLOWED_DOC_EXTENSIONS))}"}), 400

    doc_type = request.form.get("doc_type") or "другое"
    if doc_type not in storage.DOCUMENT_TYPES:
        doc_type = "другое"
    description = (request.form.get("description") or "").strip()

    original_name = secure_filename(file.filename) or f"file.{ext}"
    stored_filename = f"{uuid.uuid4().hex[:12]}_{original_name}"
    size = document_vault.save_encrypted(stored_filename, file.read())

    meta = storage.add_document({
        "author_id": author_id,
        "original_name": file.filename,
        "stored_filename": stored_filename,
        "doc_type": doc_type,
        "description": description,
        "size": size,
        "uploaded_at": time.time(),
    })
    author = storage.get_author(author_id)
    _log("загрузил документ (зашифрован)", f"{doc_type}: {file.filename} (автор: {author['name'] if author else author_id})")
    return jsonify(meta), 201


@app.get("/api/authors/<author_id>/documents/<doc_id>/view")
def view_author_document(author_id, doc_id):
    """Просмотр документа «по месту» (inline — открывается прямо в браузере,
    не как файл для скачивания) — доступен admin, а также сотруднику с
    действующим временным разрешением (см. _can_view_author_sensitive).
    В отличие от /download — этот эндпоинт не считается «выдачей копии
    файла», это входит в сам смысл временного разрешения: посмотреть,
    но не унести с собой оригинал."""
    doc = storage.get_document(doc_id)
    if not doc or doc["author_id"] != author_id:
        return jsonify({"error": "Документ не найден"}), 404
    if not _can_view_author_sensitive(author_id):
        return jsonify({"error": "Недостаточно прав — нужна роль admin или временное разрешение на просмотр"}), 403
    raw = document_vault.read_decrypted(doc["stored_filename"])
    if raw is None:
        return jsonify({"error": "Файл отсутствует в зашифрованном хранилище"}), 404
    is_admin = (not auth.is_enabled()) or session.get("role") == "admin"
    _log(
        "просмотрел документ (администратор)" if is_admin else "просмотрел документ (по временному разрешению)",
        f"{doc['doc_type']}: {doc['original_name']}",
    )
    ext = doc["original_name"].rsplit(".", 1)[-1].lower() if "." in doc["original_name"] else ""
    mimetype = {
        "pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "tif": "image/tiff", "tiff": "image/tiff",
    }.get(ext, "application/octet-stream")
    return Response(raw, mimetype=mimetype, headers={"Content-Disposition": "inline"})


@app.get("/api/authors/<author_id>/documents/<doc_id>/download")
@require_role("admin")
def download_author_document(author_id, doc_id):
    doc = storage.get_document(doc_id)
    if not doc or doc["author_id"] != author_id:
        return jsonify({"error": "Документ не найден"}), 404
    raw = document_vault.read_decrypted(doc["stored_filename"])
    if raw is None:
        return jsonify({"error": "Файл отсутствует в зашифрованном хранилище"}), 404
    _log("скачал документ (администратор)", f"{doc['doc_type']}: {doc['original_name']}")
    from urllib.parse import quote
    ext = doc["original_name"].rsplit(".", 1)[-1] if "." in doc["original_name"] else "bin"
    ascii_name = secure_filename(doc["original_name"])
    if not ascii_name.strip("-_"):  # чисто кириллическое имя — secure_filename отдаёт "" или "-"
        ascii_name = f"document.{ext}"
    utf8_name = quote(doc["original_name"])
    return Response(
        raw,
        mimetype="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={ascii_name}; filename*=UTF-8''{utf8_name}"},
    )


@app.delete("/api/authors/<author_id>/documents/<doc_id>")
@require_role("admin")
def delete_author_document(author_id, doc_id):
    doc = storage.get_document(doc_id)
    if not doc or doc["author_id"] != author_id:
        return jsonify({"error": "Документ не найден"}), 404
    storage.delete_document(doc_id)
    document_vault.delete_encrypted(doc["stored_filename"])
    _log("удалил документ", f"{doc['doc_type']}: {doc['original_name']}")
    return jsonify({"ok": True})


# ---------- документы сотрудника (доверенность от фирмы и т.п., подающего заявления) ----------
# В отличие от документов автора — это личные документы залогиненного
# сотрудника, доступ только к своим (не нужна проверка на admin). Но
# загрузка/удаление — это изменение данных, а по правилам приложения роль
# «только просмотр» ничего не может менять (см. подсказку в разделе
# «Доступ») — поэтому на POST/DELETE стоит require_role("editor"), а
# просмотр/скачивание своих же документов оставлен любому вошедшему,
# это чтение, не изменение.
def _require_login_username():
    username = session.get("username")
    if not username:
        return None, (jsonify({"error": "Нужен вход в систему"}), 401)
    return username, None


def _can_view_author_sensitive(author_id):
    """admin — всегда; иначе — только если выдано действующее временное
    разрешение именно на этого автора (или на всех авторов сразу), см.
    storage.has_active_document_grant. Используется для ПРОСМОТРА
    документов/личных данных автора — скачивание исходного файла
    (download_author_document) по-прежнему только у admin."""
    if not auth.is_enabled():
        return True
    if session.get("role") == "admin":
        return True
    username = session.get("username")
    return bool(username) and storage.has_active_document_grant(username, author_id)


@app.get("/api/me/documents")
def list_my_documents():
    username, err = _require_login_username()
    if err:
        return err
    return jsonify(storage.get_employee_documents(username))


@app.post("/api/me/documents")
@require_role("editor")
def upload_my_document():
    username, err = _require_login_username()
    if err:
        return err
    if "file" not in request.files:
        return jsonify({"error": "Файл не передан"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Файл не выбран"}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_DOC_EXTENSIONS:
        return jsonify({"error": f"Недопустимый тип файла .{ext}. Разрешены: {', '.join(sorted(ALLOWED_DOC_EXTENSIONS))}"}), 400

    description = (request.form.get("description") or "").strip()

    original_name = secure_filename(file.filename) or f"file.{ext}"
    stored_filename = f"employee_{uuid.uuid4().hex[:12]}_{original_name}"
    size = document_vault.save_encrypted(stored_filename, file.read())

    meta = storage.add_employee_document({
        "username": username,
        "original_name": file.filename,
        "stored_filename": stored_filename,
        "description": description,
        "size": size,
        "uploaded_at": time.time(),
    })
    _log("загрузил свой документ (зашифрован)", file.filename)
    return jsonify(meta), 201


@app.get("/api/me/documents/<doc_id>/download")
def download_my_document(doc_id):
    username, err = _require_login_username()
    if err:
        return err
    doc = storage.get_employee_document(doc_id)
    if not doc or doc["username"] != username:
        return jsonify({"error": "Документ не найден"}), 404
    raw = document_vault.read_decrypted(doc["stored_filename"])
    if raw is None:
        return jsonify({"error": "Файл отсутствует в зашифрованном хранилище"}), 404
    from urllib.parse import quote
    ext = doc["original_name"].rsplit(".", 1)[-1] if "." in doc["original_name"] else "bin"
    ascii_name = secure_filename(doc["original_name"])
    if not ascii_name.strip("-_"):
        ascii_name = f"document.{ext}"
    utf8_name = quote(doc["original_name"])
    return Response(
        raw,
        mimetype="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={ascii_name}; filename*=UTF-8''{utf8_name}"},
    )


@app.delete("/api/me/documents/<doc_id>")
@require_role("editor")
def delete_my_document(doc_id):
    username, err = _require_login_username()
    if err:
        return err
    doc = storage.get_employee_document(doc_id)
    if not doc or doc["username"] != username:
        return jsonify({"error": "Документ не найден"}), 404
    storage.delete_employee_document(doc_id)
    document_vault.delete_encrypted(doc["stored_filename"])
    _log("удалил свой документ", doc["original_name"])
    return jsonify({"ok": True})


# ---------- личные данные автора-истца (зашифрованы, полный доступ у admin, просмотр — по разрешению) ----------
@app.get("/api/authors/<author_id>/personal-data")
def get_author_personal_data(author_id):
    if not storage.get_author(author_id):
        return jsonify({"error": "Автор не найден"}), 404
    if not _can_view_author_sensitive(author_id):
        return jsonify({"error": "Недостаточно прав — нужна роль admin или временное разрешение на просмотр"}), 403
    fields = author_personal_data.get(author_id)
    return jsonify(fields or {k: "" for k in author_personal_data.FIELDS})


@app.put("/api/authors/<author_id>/personal-data")
@require_role("admin")
def save_author_personal_data(author_id):
    author = storage.get_author(author_id)
    if not author:
        return jsonify({"error": "Автор не найден"}), 404
    data = request.get_json(force=True)
    fields = {k: (data.get(k) or "").strip() for k in author_personal_data.FIELDS}
    author_personal_data.save(author_id, fields)
    _log("сохранил личные данные автора", author["name"])
    return jsonify({"ok": True})


@app.get("/api/authors/<author_id>/personal-data/for-petition")
@require_role("editor")
def preview_author_personal_data_for_petition(author_id):
    """Единственная точка, где обычный сотрудник (не admin) может увидеть
    личные данные автора — только для чтения, и только в контексте
    подготовки заявления в суд (чтобы можно было заметить ошибку в паспорте
    или устаревший адрес до подачи). Каждый такой просмотр обязательно
    попадает в журнал действий.

    Отдаёт ТОЛЬКО те поля, которые реально нужны для заявления с учётом
    entity_type — не весь словарь целиком. Физлицу сотрудник не должен
    видеть чужие поля юрлица (там их просто нет), а юрлицу/ИП — наоборот,
    не должен видеть паспорт и адрес регистрации физлица, даже если они
    случайно остались в записи от прошлого переключения статуса. Коммерческие
    условия (номер договора, плата) тем более не нужны для проверки данных
    истца перед заявлением — сюда не попадают вовсе."""
    author = storage.get_author(author_id)
    if not author:
        return jsonify({"error": "Автор не найден"}), 404
    fields = author_personal_data.get(author_id)
    if not fields:
        return jsonify({"error": "У этого автора ещё не заполнены личные данные — попросите администратора внести их в разделе «Заказчик и реквизиты»"}), 409

    entity_type = fields.get("entity_type") or "individual"
    if entity_type == "individual":
        relevant_keys = ("full_name", "birth_place", "passport", "issued_by", "snils")
    else:
        relevant_keys = ("org_name", "org_inn", "org_kpp", "org_address", "org_representative")
    relevant = {"entity_type": entity_type}
    relevant.update({k: fields.get(k, "") for k in relevant_keys})

    _log("сотрудник просмотрел личные данные автора (при подготовке заявления)", author["name"])
    return jsonify(relevant)


# ---------- подготовка заявления в суд (единственный способ сотруднику "коснуться" защищённых данных) ----------
@app.post("/api/authors/<author_id>/court-petition")
@require_role("editor")
def prepare_court_petition(author_id):
    """Запускает сборку заявления в фоне и сразу отвечает job_id — сама
    сборка (расшифровка документов, чтение скриншотов, упаковка в zip)
    вынесена в фоновый поток (см. jobs.start_petition_job), чтобы не
    блокировать сервер на всё время сборки при одном gunicorn-воркере.
    Всё, что нужно проверить синхронно (права доступа, чьи это дела, не
    подано ли уже) — проверяется здесь же, до запуска фоновой задачи,
    чтобы явные ошибки пользователь видел сразу, а не после ожидания."""
    author = storage.get_author(author_id)
    if not author:
        return jsonify({"error": "Автор не найден"}), 404

    data = request.get_json(force=True)
    case_ids = data.get("case_ids") or []
    if not case_ids:
        return jsonify({"error": "Не выбрано ни одного дела"}), 400

    cases = []
    seen_urls = set()
    for cid in case_ids:
        case = storage.get_blocking_case(cid)
        if not case or case.get("author_name") != author["name"]:
            return jsonify({"error": f"Дело {cid} не найдено или относится к другому автору"}), 400
        # решение по обращению «отклонено»/«нет реакции» — самостоятельный
        # сигнал «нужно переподавать», не только needs_resend от
        # автоматической проверки ссылки (см. link_check.appeal_failed,
        # та же логика используется и на фронтенде)
        if case.get("petition_filed_at") and not case.get("needs_resend") and not link_check.appeal_failed(case):
            return jsonify({"error": f"По ссылке {case.get('url')} заявление уже отмечено как поданное ({case['petition_filed_at']}) — уберите его из выбора, чтобы не подавать повторно"}), 400
        if case.get("url") in seen_urls:
            continue  # одна и та же ссылка выбрана дважды — просто не дублируем в заявлении
        seen_urls.add(case.get("url"))
        cases.append(case)

    personal_fields = author_personal_data.get(author_id)
    if not personal_fields:
        return jsonify({"error": "У этого автора ещё не заполнены личные данные — попросите администратора внести их в карточке автора"}), 409

    # submitting_username считываем здесь (в основном потоке, откуда есть
    # доступ к session) — внутри фоновой задачи Flask-сессии уже не будет.
    submitting_username = session.get("username")

    def build_fn():
        return _build_petition_zip(author, author_id, cases, personal_fields, submitting_username)

    job_id = jobs.start_petition_job(build_fn)
    return jsonify({"job_id": job_id}), 202


@app.get("/api/authors/<author_id>/court-petition/<job_id>")
@require_role("editor")
def poll_court_petition(author_id, job_id):
    job = jobs.get_petition_job(job_id)
    if not job:
        return jsonify({"error": "Задача не найдена"}), 404
    if job["status"] in ("queued", "running"):
        return jsonify({"status": job["status"]})
    if job["status"] == "error":
        return jsonify({"status": "error", "error": job.get("error", "Не удалось подготовить заявление")})
    return jsonify({"status": "done"})


@app.get("/api/authors/<author_id>/court-petition/<job_id>/download")
@require_role("editor")
def download_court_petition(author_id, job_id):
    job = jobs.get_petition_job(job_id)
    if not job:
        return jsonify({"error": "Задача не найдена"}), 404
    if job["status"] != "done":
        return jsonify({"error": "Заявление ещё не готово"}), 409
    result = job["result"]
    return Response(
        result["zip_bytes"],
        mimetype="application/zip",
        headers={"Content-Disposition": f"attachment; filename={result['filename_ascii']}; filename*=UTF-8''{result['filename_utf8']}"},
    )


def _build_petition_zip(author, author_id, cases, personal_fields, submitting_username):
    """Собственно сборка zip — вызывается в фоновом потоке (см.
    jobs.start_petition_job). Возвращает (zip_bytes, filename_ascii, filename_utf8).

    Структура архива — сознательно всего 2 папки, а не по подпапке на
    каждое дело, как было раньше:
      «нарушения/»        — заявление.docx + один общий склеенный файл
                             скриншотов нарушений + один общий склеенный
                             файл скриншотов подтверждения хостинга/IP
                             (по всем выбранным делам сразу — см.
                             image_stamp.combine_vertically, добавлено
                             03.09 по прямой просьбе пользователя: раньше
                             был отдельный PNG на каждое дело, при
                             заявлении сразу по многим ссылкам архив было
                             неудобно просматривать)
      «документы автора/» — документы автора (не дублируются на каждое
                             дело — один общий комплект) + документы
                             сотрудника, подающего заявление"""
    used_docs, used_shots, used_employee_docs = [], [], []
    # Счётчики для раздела "Приложения" в самом заявлении (см. petition.py,
    # _ATTACHMENT_LABELS) — считаются по тем же файлам, что реально попадут
    # в архив ниже, а не отдельным проходом, чтобы числа не могли разойтись.
    attachment_counts = {
        "violation_screenshots": 0, "ip_screenshots": 0,
        "power_of_attorney": 0, "copyright_proof": 0,
        "other_author_docs": 0, "employee_docs": 0,
    }
    _DOC_TYPE_TO_COUNTER = {
        "доверенность": "power_of_attorney",
        "подтверждение авторства": "copyright_proof",
    }
    # Договор (и допсоглашения, которые обычно хранятся под тем же типом)
    # не нужны в заявлении в суд — это коммерческие документы отношений
    # с автором, к предмету иска не относятся. Исключаем полностью, а не
    # просто не считаем — раньше файл всё равно попадал в архив, даже
    # не отражаясь в счётчике "Приложения".
    _EXCLUDED_DOC_TYPES = {"договор"}

    def _author_docs_for_petition():
        return [d for d in storage.get_author_documents(author_id) if d["doc_type"] not in _EXCLUDED_DOC_TYPES]

    for case in cases:
        for shot in storage.get_case_screenshots(case["id"]):
            shot_path = os.path.join(storage.SCREENSHOTS_DIR, shot["stored_filename"])
            if os.path.exists(shot_path):
                attachment_counts["ip_screenshots" if shot.get("purpose") == "defendant_proof" else "violation_screenshots"] += 1

    for doc in _author_docs_for_petition():
        attachment_counts[_DOC_TYPE_TO_COUNTER.get(doc["doc_type"], "other_author_docs")] += 1

    if submitting_username:
        attachment_counts["employee_docs"] += len(storage.get_employee_documents(submitting_username))

    petition_bytes = petition.build_petition_docx(personal_fields, author["name"], cases, attachment_counts)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("нарушения/заявление.docx", petition_bytes)

        # Скриншоты нарушений и подтверждения хостинга/IP склеиваются в
        # ОДИН файл на каждую категорию (не по файлу на каждое дело, как
        # было раньше) — по прямой просьбе пользователя (см. заметку
        # разработки, 03.09): при заявлении сразу по многим выделенным
        # ссылкам архив с десятками отдельных PNG неудобно просматривать.
        # Порядок внутри каждого файла — тот же, в каком идут выбранные
        # дела; каждый сегмент уже содержит собственную плашку (домен/IP/
        # дата), так что даже без подписи между сегментами видно, к
        # какой именно ссылке относится каждая часть картинки.
        violation_shot_bytes = []
        ip_shot_bytes = []
        for case in cases:
            for shot in storage.get_case_screenshots(case["id"]):
                shot_path = os.path.join(storage.SCREENSHOTS_DIR, shot["stored_filename"])
                if not os.path.exists(shot_path):
                    continue
                with open(shot_path, "rb") as f:
                    raw_shot = f.read()
                if shot.get("purpose") == "defendant_proof":
                    ip_shot_bytes.append(raw_shot)
                else:
                    violation_shot_bytes.append(raw_shot)
                used_shots.append(shot["original_name"])

        combined_violations = image_stamp.combine_vertically(violation_shot_bytes)
        if combined_violations is not None:
            zf.writestr("нарушения/скриншоты нарушений.png", combined_violations)
        combined_ip = image_stamp.combine_vertically(ip_shot_bytes)
        if combined_ip is not None:
            zf.writestr("нарушения/скриншоты IP-хостинга.png", combined_ip)

        for doc in _author_docs_for_petition():
            raw = document_vault.read_decrypted(doc["stored_filename"])
            if raw is not None:
                zf.writestr(f"документы автора/{doc['doc_type']} — {doc['original_name']}", raw)
                used_docs.append(doc["original_name"])

        # документы того, кто СЕЙЧАС готовит заявление (доверенность от
        # фирмы и т.п.) — не документы автора, а документы конкретного
        # сотрудника, у каждого свой набор. Кладём в ту же папку
        # «документы автора», чтобы всего было 2 папки в архиве, как и
        # требовалось — с явным префиксом в имени файла, чтобы не
        # перепутать с документами самого автора.
        if submitting_username:
            for doc in storage.get_employee_documents(submitting_username):
                raw = document_vault.read_decrypted(doc["stored_filename"])
                if raw is not None:
                    zf.writestr(f"документы автора/специалист — {doc['original_name']}", raw)
                    used_employee_docs.append(doc["original_name"])

    # ВАЖНО: это выполняется в фоновом потоке (см. jobs.start_petition_job),
    # где нет активного Flask-запроса — обычный _log() здесь упадёт с
    # "Working outside of request context", потому что читает session
    # изнутри. submitting_username поэтому передаётся явным аргументом,
    # считанным из session ещё в основном потоке, до запуска фоновой
    # задачи (см. вызывающую функцию prepare_court_petition).
    storage.log_action(
        submitting_username,
        "подготовил заявление в суд",
        f"автор: {author['name']}; дела: {', '.join(c['url'] for c in cases)}; "
        f"использованы документы: {', '.join(used_docs) or 'нет'}; "
        f"документы сотрудника: {', '.join(used_employee_docs) or 'нет'}; "
        f"использованы скриншоты: {', '.join(used_shots) or 'нет'}",
    )

    buf.seek(0)
    from urllib.parse import quote
    ascii_author = secure_filename(author["name"])
    if not ascii_author.strip("-_"):  # secure_filename на чистой кириллице отдаёт "" или "-" — оба варианта негодны
        ascii_author = "author"
    safe_ascii = f"zayavlenie_{ascii_author}.zip"
    utf8_name = quote(f"заявление_{author['name']}.zip")
    return buf.getvalue(), safe_ascii, utf8_name


# ---------- works (произведения) ----------
@app.get("/api/authors/<author_id>/works")
def get_author_works(author_id):
    return jsonify(storage.list_works_by_author(author_id))


def _normalize_sources(raw):
    raw = raw or {}
    return {k: bool(raw.get(k, DEFAULT_SOURCES[k])) for k in DEFAULT_SOURCES}


def _normalize_work_query(value):
    """Поле "query" у произведения — строка (один запрос, старый формат)
    или список строк (несколько вариантов формулировки, новый формат).
    Принимаем и то, и другое от фронтенда, сохраняем в том же виде."""
    if isinstance(value, list):
        return [q.strip() for q in value if isinstance(q, str) and q.strip()]
    return (value or "").strip()


@app.post("/api/works")
@require_role("editor")
def create_work():
    data = request.get_json(force=True)
    required = {"author_id", "title", "query"}
    if not required.issubset(data):
        return jsonify({"error": f"Нужны поля: {sorted(required)}"}), 400
    if not storage.get_author(data["author_id"]):
        return jsonify({"error": "Автор не найден"}), 404
    work = {
        "id": None,
        "author_id": data["author_id"],
        "title": data["title"].strip(),
        "query": _normalize_work_query(data["query"]),
        "keywords": [k.strip() for k in data.get("keywords", []) if k.strip()],
        "negative_keywords": [k.strip() for k in data.get("negative_keywords", []) if k.strip()],
        "pages": int(data.get("pages", 7)),
        "extra_blocked_domains": [d.strip().lower() for d in data.get("extra_blocked_domains", []) if d.strip()],
        "active": bool(data.get("active", True)),
        "sources": _normalize_sources(data.get("sources")),
        "customer_site_url": (data.get("customer_site_url") or "").strip(),
    }
    saved = storage.upsert_work(work)
    _log("создал произведение", work["title"])
    return jsonify(saved), 201


@app.put("/api/works/<work_id>")
@require_role("editor")
def update_work(work_id):
    existing = storage.get_work(work_id)
    if not existing:
        return jsonify({"error": "Произведение не найдено"}), 404
    data = request.get_json(force=True)
    existing.update({
        "title": (data.get("title", existing["title"])).strip(),
        "query": _normalize_work_query(data.get("query", existing["query"])),
        "keywords": [k.strip() for k in data.get("keywords", existing["keywords"]) if k.strip()],
        "negative_keywords": [k.strip() for k in data.get("negative_keywords", existing.get("negative_keywords", [])) if k.strip()],
        "pages": int(data.get("pages", existing.get("pages", 7))),
        "extra_blocked_domains": [d.strip().lower() for d in data.get("extra_blocked_domains", existing.get("extra_blocked_domains", [])) if d.strip()],
        "active": bool(data.get("active", existing.get("active", True))),
        "sources": _normalize_sources(data.get("sources", existing.get("sources"))),
        "customer_site_url": (data.get("customer_site_url", existing.get("customer_site_url", "")) or "").strip(),
    })
    storage.upsert_work(existing)
    _log("изменил произведение", existing["title"])
    return jsonify(existing)


@app.delete("/api/works/<work_id>")
@require_role("editor")
def remove_work(work_id):
    existing = storage.get_work(work_id)
    storage.delete_work(work_id)
    _log("удалил произведение", existing["title"] if existing else work_id)
    return jsonify({"ok": True})


# ---------- blocklist ----------
@app.get("/api/blocklist")
def get_blocklist():
    return jsonify(storage.load_blocklist())


@app.post("/api/blocklist")
@require_role("admin")
def set_blocklist():
    data = request.get_json(force=True)
    domains = data.get("domains", [])
    storage.save_blocklist(domains)
    _log("изменил общий блок-лист", f"{len(domains)} доменов")
    return jsonify(storage.load_blocklist())


# ---------- поиск по сайтам (отдельный раздел) ----------
@app.get("/api/sites")
def list_sites():
    return jsonify(storage.load_sites())


@app.post("/api/sites")
@require_role("editor")
def create_site():
    """Добавить сайт в справочник может любой редактор (раньше — только
    admin или по временному разрешению: из-за этого новые пиратские сайты
    не удавалось добавить). Изменение и удаление по-прежнему требуют
    admin или разрешения — там можно испортить чужую настройку."""
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    url_template = (data.get("url_template") or "").strip()
    site_type = data.get("type") or "auto"
    if not name or not url_template:
        return jsonify({"error": "Укажите название и адрес/шаблон ссылки"}), 400
    if "://" not in url_template:
        url_template = "https://" + url_template
    if site_type == "generic" and "{query}" not in url_template:
        return jsonify({"error": "В шаблоне ссылки должен быть плейсхолдер {query}"}), 400
    new_base = chronic_links._base_domain(urlparse(url_template.replace("{query}", "q")).hostname or "")
    if not new_base:
        return jsonify({"error": "Не удалось определить домен из адреса"}), 400
    for existing in storage.load_sites():
        host = urlparse((existing.get("url_template") or "").replace("{query}", "q")).hostname or ""
        if chronic_links._base_domain(host) == new_base:
            return jsonify({
                "error": f"Сайт с доменом {new_base} уже есть в справочнике: «{existing.get('name', '')}»",
                "existing_site_id": existing.get("id"),
            }), 409
    extra, err = _site_optional_fields(data, url_template)
    if err:
        return jsonify({"error": err}), 400
    site = storage.upsert_site({"id": None, "name": name, "url_template": url_template.rstrip("/"), "type": site_type, **extra})
    _log("добавил сайт в справочник", f"{name}: {site['url_template']}")
    return jsonify(site), 201


@app.put("/api/sites/<site_id>")
@require_role("editor")
@require_site_edit_access
def update_site(site_id):
    existing = storage.get_site(site_id)
    if not existing:
        return jsonify({"error": "Сайт не найден"}), 404
    data = request.get_json(force=True)
    name = (data.get("name") or existing["name"]).strip()
    url_template = (data.get("url_template") or existing["url_template"]).strip()
    site_type = data.get("type", existing.get("type", "auto"))
    if site_type == "generic" and "{query}" not in url_template:
        return jsonify({"error": "В шаблоне ссылки должен быть плейсхолдер {query}"}), 400
    patch = {"name": name, "url_template": url_template.rstrip("/"), "type": site_type}
    extra, err = _site_optional_fields(data, url_template)
    if err:
        return jsonify({"error": err}), 400
    patch.update(extra)
    existing.update(patch)
    storage.upsert_site(existing)
    return jsonify(existing)


def _site_optional_fields(data, url_template):
    """Дополнительные настройки сайта (обновление 23.09) — все необязательные.
    Возвращает (patch, ошибка)."""
    patch = {}
    if "mode" in data:
        if data["mode"] not in site_search.SITE_MODES:
            return {}, f"Недопустимый режим. Разрешены: {list(site_search.SITE_MODES)}"
        if data["mode"] == "template" and "{query}" not in url_template:
            return {}, "Для режима «только по шаблону» в адресе нужен {query}"
        patch["mode"] = data["mode"]
    if "priority" in data:
        if data["priority"] not in ("high", "normal", "low"):
            return {}, "Приоритет: high, normal или low"
        patch["priority"] = data["priority"]
    if "mirrors" in data:
        mirrors = data["mirrors"] if isinstance(data["mirrors"], list) else str(data["mirrors"]).split("\n")
        patch["mirrors"] = [m.strip() for m in mirrors if m and m.strip()][:50]
    if "notes" in data:
        patch["notes"] = str(data["notes"] or "")[:2000]
    return patch, None


@app.post("/api/sites/<site_id>/test")
@require_role("editor")
def test_site(site_id):
    """«Проверить настройку»: один поиск по одному сайту, сразу видно,
    работает ли шаблон. Ничего не меняет, кроме статуса последней проверки."""
    site = storage.get_site(site_id)
    if not site:
        return jsonify({"error": "Сайт не найден"}), 404
    query = ((request.get_json(silent=True) or {}).get("query") or "").strip()
    if not query:
        return jsonify({"error": "Введите слово или фразу для проверки"}), 400
    test_site_copy = dict(site)
    if test_site_copy.get("mode") in site_search.SKIPPED_MODES:
        test_site_copy["mode"] = "auto"  # проверка настройки — всё равно пробуем найти
    report = {}
    results, errors, _redirects = site_search.search_sites([test_site_copy], [query], report=report)
    r = report.get(site_id, {})
    jobs._save_site_statuses({site_id: r} if site.get("mode") not in site_search.SKIPPED_MODES else {})
    status = r.get("status") or "error"
    return jsonify({
        "status": status,
        "status_label": site_search.STATUS_LABELS.get(status, status),
        "detail": r.get("detail") or (errors[0]["error"] if errors else ""),
        "found": len(results),
        "sample": [{"title": x.get("title", ""), "url": x.get("url", "")} for x in results[:5]],
    })


CERT_RENEWAL_CONF = "/etc/letsencrypt/renewal/piracy-monitor-ip.conf"


def _https_cert_expiry(host="127.0.0.1", port=443):
    """Срок действия сертификата, который реально отдаёт веб-сервер.
    Читается с самого соединения, а не из файла — так не нужны права на
    /etc/letsencrypt, и проверяется ровно то, что видят браузеры."""
    import socket
    import ssl
    from datetime import timezone
    from cryptography import x509
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=5) as sock:
        with ctx.wrap_socket(sock) as tls:
            der = tls.getpeercert(binary_form=True)
    cert = x509.load_der_x509_certificate(der)
    not_after = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after.replace(tzinfo=timezone.utc)
    return not_after


@app.get("/api/admin/cert-status")
@require_role("admin")
def cert_status():
    """Для предупреждения администратору: сертификат Let's Encrypt на IP
    живёт ~6 дней и продлевается автоматически; если продление сломалось,
    об этом лучше узнать за пару дней, а не когда браузеры начнут
    показывать «сайт небезопасен»."""
    if not os.path.exists(CERT_RENEWAL_CONF):
        return jsonify({"monitored": False})
    try:
        not_after = _https_cert_expiry()
        days_left = (not_after.timestamp() - time.time()) / 86400
        return jsonify({"monitored": True, "not_after": not_after.isoformat(), "days_left": round(days_left, 2)})
    except Exception as e:  # noqa
        return jsonify({"monitored": True, "error": f"{type(e).__name__}: {e}"[:300]})


@app.get("/api/admin/yandex-compare")
@require_role("admin")
def yandex_compare_summary():
    """Итоги режима сравнения выдачи Яндекса (YANDEX_RESPONSE_FORMAT=compare):
    по скольким страницам XML нашёл не меньше HTML, сколько было ошибок."""
    entries = storage.load_yandex_compare()
    ok = [e for e in entries if e.get("xml_count") is not None]
    not_worse = sum(1 for e in ok if e["xml_count"] >= e.get("html_count", 0))
    only_html = sum(len(set(e.get("html_urls", [])) - set(e.get("xml_urls", []))) for e in ok)
    only_xml = sum(len(set(e.get("xml_urls", [])) - set(e.get("html_urls", []))) for e in ok)
    return jsonify({
        "pages_compared": len(entries), "xml_errors": len(entries) - len(ok),
        "xml_not_worse": not_worse, "urls_only_in_html": only_html, "urls_only_in_xml": only_xml,
        "html_total": sum(e.get("html_count", 0) for e in ok), "xml_total": sum(e.get("xml_count", 0) for e in ok),
        "mode": yandex_search.response_format_mode(),
    })


@app.post("/api/sites/<site_id>/apply-redirect")
@require_role("editor")
@require_site_edit_access
def apply_site_redirect(site_id):
    """Меняет только домен в уже существующем шаблоне ссылки сайта, сохраняя
    остальной путь/параметры (в т.ч. плейсхолдер {query}, если он был) —
    используется кнопкой «Обновить адрес» у уведомления о переезде сайта на
    другой домен. В отличие от обычного PUT (который ожидает полностью
    готовый шаблон целиком), этот эндпоинт безопасен для сайтов со строгим
    типом «generic», где домен без {query} не прошёл бы валидацию."""
    existing = storage.get_site(site_id)
    if not existing:
        return jsonify({"error": "Сайт не найден"}), 404
    data = request.get_json(force=True)
    new_domain = (data.get("new_domain") or "").strip()
    if not new_domain:
        return jsonify({"error": "Укажите новый домен"}), 400

    old_parsed = urlparse(existing["url_template"])
    new_url_template = existing["url_template"].replace(
        f"{old_parsed.scheme}://{old_parsed.netloc}",
        f"{old_parsed.scheme}://{new_domain}",
        1,
    )
    existing["url_template"] = new_url_template.rstrip("/")
    mirrors = list(existing.get("mirrors") or [])
    if old_parsed.netloc and old_parsed.netloc not in mirrors:
        mirrors.append(old_parsed.netloc)  # старый адрес — в зеркала, а не в никуда
    existing["mirrors"] = mirrors
    storage.upsert_site(existing)
    _log("обновил адрес сайта после переезда", f"{existing['name']}: {old_parsed.netloc} -> {new_domain}")
    return jsonify(existing)


@app.delete("/api/sites/<site_id>")
@require_role("editor")
@require_site_edit_access
def remove_site(site_id):
    storage.delete_site(site_id)
    return jsonify({"ok": True})


@app.post("/api/sites/search")
@require_role("editor")
def search_across_sites():
    """Запускает поиск по сайтам как фоновую задачу (не ждёт результата
    синхронно) — со справочником в полторы сотни доменов один блокирующий
    HTTP-запрос до конца прохода по всем был бы непрактично долгим и без
    какого-либо прогресса на экране. Прогресс и результат — через опрос
    /api/sites/search-jobs/<job_id>, тем же способом, что и для обычного
    поиска по произведениям.

    Принимает либо "queries" (список — можно сколько угодно вариантов
    запроса за один прогон, каждый сайт проверяется по каждому), либо
    старое "query" (одна строка) для обратной совместимости."""
    data = request.get_json(force=True)
    queries = data.get("queries")
    if queries is None:
        single = (data.get("query") or "").strip()
        queries = [single] if single else []
    else:
        queries = [q.strip() for q in queries if isinstance(q, str) and q.strip()]
    if not queries:
        return jsonify({"error": "Укажите хотя бы один запрос"}), 400

    site_ids = data.get("site_ids")  # необязательно: искать только по части сайтов
    sites = storage.load_sites()
    if site_ids:
        sites = [s for s in sites if s["id"] in site_ids]
    if not sites:
        return jsonify({"error": "Список сайтов пуст — добавьте хотя бы один в справочнике"}), 400

    negative_keywords = [w.strip() for w in (data.get("negative_keywords") or []) if isinstance(w, str) and w.strip()]

    job_id = jobs.start_site_search_job(sites, queries, negative_keywords)
    return jsonify({"job_id": job_id, "sites_total": len(sites), "queries_total": len(queries)}), 202


@app.get("/api/sites/search-jobs/<job_id>")
def get_site_search_job(job_id):
    job = jobs.get_site_search_job(job_id)
    if not job:
        return jsonify({"error": "Задача не найдена"}), 404
    return jsonify(job)


@app.post("/api/sites/search-jobs/<job_id>/cancel")
@require_role("editor")
def cancel_site_search_job(job_id):
    job = jobs.cancel_site_search_job(job_id)
    if not job:
        return jsonify({"error": "Задача не найдена"}), 404
    _log("остановил поиск по сайтам", job_id)
    return jsonify(job)


@app.get("/api/sites/last-search-results")
def get_last_site_search_results():
    """Последний результат «Поиск по сайтам», сохранённый на диске — чтобы
    он не пропадал при закрытии приложения/перезапуске сервера (сама
    задача поиска, jobs._site_jobs, живёт только в памяти процесса).
    Возвращает null в поле result, если ничего ещё не искали."""
    saved = storage.load_last_site_search_result()
    if not saved:
        return jsonify({"result": None, "saved_at": None})
    return jsonify(saved)


# ---------- сохранённые результаты (отдельно от разовых job) ----------
@app.get("/api/works/<work_id>/results")
def get_work_results(work_id):
    if not storage.get_work(work_id):
        return jsonify({"error": "Произведение не найдено"}), 404
    return jsonify(storage.load_work_results(work_id))


@app.post("/api/works/<work_id>/results")
@require_role("editor")
def add_work_result(work_id):
    if not storage.get_work(work_id):
        return jsonify({"error": "Произведение не найдено"}), 404
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Укажите ссылку"}), 400
    row = {
        "position": None,
        "source": (data.get("source") or "Добавлено вручную").strip(),
        "title": (data.get("title") or "").strip() or url,
        "description": (data.get("description") or "").strip(),
        "url": url,
    }
    saved = storage.add_work_result_row(work_id, row)
    if saved is None:
        return jsonify({"error": "Эта ссылка уже есть в сохранённых результатах этого произведения", "already_exists": True}), 409
    return jsonify(saved), 201


@app.delete("/api/works/<work_id>/results/<row_id>")
@require_role("editor")
def delete_work_result(work_id, row_id):
    if not storage.get_work(work_id):
        return jsonify({"error": "Произведение не найдено"}), 404
    storage.delete_work_result_row(work_id, row_id)
    return jsonify({"ok": True})


@app.delete("/api/works/<work_id>/results")
@require_role("editor")
def clear_work_results(work_id):
    if not storage.get_work(work_id):
        return jsonify({"error": "Произведение не найдено"}), 404
    storage.delete_work_results(work_id)
    return jsonify({"ok": True})


@app.get("/api/works/<work_id>/results/export.csv")
def export_work_results_csv(work_id):
    work = storage.get_work(work_id)
    if not work:
        return jsonify({"error": "Произведение не найдено"}), 404
    items = storage.load_work_results(work_id)["items"]
    csv_text = exporters.results_to_csv(items)
    from urllib.parse import quote
    safe_ascii = f"results_{work_id}.csv"
    utf8_name = quote(f"{work['title']}_{work_id}.csv".replace(" ", "_"))
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={safe_ascii}; filename*=UTF-8''{utf8_name}"},
    )


# ---------- jobs (runs) ----------
@app.post("/api/works/<work_id>/run")
@require_role("editor")
def run_work(work_id):
    work = storage.get_work(work_id)
    if not work:
        return jsonify({"error": "Произведение не найдено"}), 404
    author = storage.get_author(work["author_id"])
    job_id = jobs.start_job(work, author["name"] if author else "")
    return jsonify({"job_id": job_id}), 202


STAGGER_SECONDS = 4  # интервал между стартами последовательных задач при массовом запуске


def _start_staggered(works, batch_id=None):
    """Запускает список произведений как фоновые задачи, разнесённые во
    времени — общая логика для «по всем активным» и «по одному автору».

    batch_id, если передан, — привязывает завершение каждой задачи к
    прогрессу пакетного запуска (storage.mark_bulk_search_work_finished),
    чтобы прогресс переживал перезапуск сервера и можно было продолжить
    прерванный запуск позже, а не начинать с нуля."""
    authors_by_id = {a["id"]: a["name"] for a in storage.load_authors()}
    started = []
    for work in works:
        def on_finish(work_id, status, _batch_id=batch_id):
            if _batch_id:
                storage.mark_bulk_search_work_finished(_batch_id, work_id, status)
        job_id = jobs.start_job(
            work, authors_by_id.get(work["author_id"], ""),
            start_delay=len(started) * STAGGER_SECONDS,
            on_finish=on_finish if batch_id else None,
        )
        started.append({"work_id": work["id"], "job_id": job_id})
    return started


@app.post("/api/works/run-all")
@require_role("editor")
def run_all_active_works():
    """Запускает поиск по всем произведениям с признаком «активно» — по всем
    авторам разом. Каждое произведение стартует как отдельная фоновая задача
    (тот же механизм, что и запуск одного произведения), можно свободно
    переключаться между разделами, пока все они выполняются параллельно.

    Старты специально разнесены во времени (не все залпом) — иначе при
    большом числе произведений одновременный шквал запросов к Yandex Search
    API упирается в лимит (429 Too Many Requests). Сам HTTP-ответ при этом
    не задерживается — задача просто «ждёт» своей очереди со статусом
    queued, реальная работа начинается позже.

    Прогресс сохраняется на диск (storage.start_bulk_search_batch) — если
    сервер перезапустится посреди большого запуска, ничего не потеряется:
    можно будет продолжить только с тех произведений, что не успели
    обработаться, через /api/works/run-all/resume."""
    active_works = [w for w in storage.load_works() if w.get("active", True)]
    batch_id = str(uuid.uuid4())[:12]
    storage.start_bulk_search_batch(batch_id, [w["id"] for w in active_works], "всем активным")
    started = _start_staggered(active_works, batch_id)
    _log("запустил массовый поиск", f"{len(started)} произведений")
    return jsonify({"started": started, "count": len(started), "batch_id": batch_id}), 202


@app.post("/api/authors/<author_id>/run-all")
@require_role("editor")
def run_all_active_works_for_author(author_id):
    """То же самое, что «по всем активным», но только для произведений
    конкретного автора — та же разнесённая по времени фоновая задача на
    каждое, чтобы не упереться в лимит API, даже если у автора их много."""
    author = storage.get_author(author_id)
    if not author:
        return jsonify({"error": "Автор не найден"}), 404
    active_works = [
        w for w in storage.load_works()
        if w["author_id"] == author_id and w.get("active", True)
    ]
    batch_id = str(uuid.uuid4())[:12]
    storage.start_bulk_search_batch(batch_id, [w["id"] for w in active_works], f"автору {author['name']}")
    started = _start_staggered(active_works, batch_id)
    _log("запустил поиск по всем произведениям автора", f"{author['name']}: {len(started)} произведений")
    return jsonify({"started": started, "count": len(started), "batch_id": batch_id}), 202


@app.get("/api/works/run-all/resumable")
def get_resumable_bulk_batch():
    """Есть ли незавершённый массовый запуск с прошлого раза (например,
    сервер перезапустился посреди него, или вкладку закрыли) — фронтенд
    вызывает это при открытии, чтобы предложить «Продолжить», если да."""
    batch = storage.load_bulk_search_batch()
    if not batch:
        return jsonify({"resumable": False})

    done_ids = {wid for wid, s in batch.get("work_status", {}).items() if s.get("status") == "done"}
    all_ids = set(batch["work_ids"])
    # проверяем, что «оставшиеся» произведения ещё реально существуют и активны —
    # иначе можно предложить продолжить с уже удалённым/выключенным произведением
    existing_active_ids = {w["id"] for w in storage.load_works() if w.get("active", True)}
    remaining_ids = (all_ids - done_ids) & existing_active_ids

    if not remaining_ids:
        return jsonify({"resumable": False})
    return jsonify({
        "resumable": True,
        "batch_id": batch["id"],
        "scope_label": batch.get("scope_label", ""),
        "total": len(all_ids),
        "done": len(done_ids),
        "remaining": len(remaining_ids),
        "started_at": batch["started_at"],
    })


@app.post("/api/works/run-all/resume")
@require_role("editor")
def resume_bulk_search():
    """Продолжает последний незавершённый массовый запуск — запускает
    только те произведения, что ещё не успели обработаться (или упали с
    ошибкой/были отменены), пропуская уже готовые."""
    batch = storage.load_bulk_search_batch()
    if not batch:
        return jsonify({"error": "Нет прерванного запуска для продолжения"}), 404

    done_ids = {wid for wid, s in batch.get("work_status", {}).items() if s.get("status") == "done"}
    all_works_by_id = {w["id"]: w for w in storage.load_works() if w.get("active", True)}
    remaining_works = [
        all_works_by_id[wid] for wid in batch["work_ids"]
        if wid in all_works_by_id and wid not in done_ids
    ]
    if not remaining_works:
        return jsonify({"error": "Продолжать нечего — все произведения уже обработаны"}), 400

    started = _start_staggered(remaining_works, batch["id"])
    _log("продолжил прерванный массовый поиск", f"{len(started)} произведений")
    return jsonify({"started": started, "count": len(started), "batch_id": batch["id"]}), 202


@app.delete("/api/works/run-all/resumable")
@require_role("editor")
def dismiss_resumable_bulk_batch():
    """«Не продолжать» — явный отказ от прерванного запуска, чтобы
    предложение больше не всплывало."""
    storage.clear_bulk_search_batch()
    return jsonify({"ok": True})


@app.get("/api/jobs")
def get_jobs():
    return jsonify(jobs.list_jobs())


@app.get("/api/jobs/<job_id>")
def get_job(job_id):
    job = jobs.get_job(job_id)
    if not job:
        return jsonify({"error": "Задача не найдена"}), 404
    return jsonify(job)


@app.post("/api/jobs/<job_id>/cancel")
@require_role("editor")
def cancel_job(job_id):
    job = jobs.cancel_job(job_id)
    if not job:
        return jsonify({"error": "Задача не найдена"}), 404
    _log("остановил поиск", job.get("work_title", job_id))
    return jsonify(job)


@app.post("/api/jobs/cancel-all")
@require_role("editor")
def cancel_all_jobs():
    cancelled = jobs.cancel_all_jobs()
    _log("остановил все поисковые задачи", f"{len(cancelled)} шт.")
    return jsonify({"cancelled": cancelled, "count": len(cancelled)})


@app.get("/api/jobs/<job_id>/export.csv")
def export_job_csv(job_id):
    job = jobs.get_job(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "Результаты ещё не готовы"}), 400
    scope = request.args.get("scope", "filtered")
    items = job["result"]["all_results"] if scope == "all" else job["result"]["results"]
    csv_text = exporters.results_to_csv(items)
    safe_ascii = f"results_{job_id}.csv"
    from urllib.parse import quote
    suffix = "_все" if scope == "all" else ""
    utf8_name = quote(f"{job['work_title']}{suffix}_{job_id}.csv".replace(" ", "_"))
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={safe_ascii}; filename*=UTF-8''{utf8_name}"},
    )


@app.post("/api/jobs/<job_id>/send-telegram")
@require_role("editor")
def send_job_telegram(job_id):
    job = jobs.get_job(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "Результаты ещё не готовы"}), 400
    try:
        exporters.send_telegram_summary(job["work_title"], job["result"], job.get("author_name", ""))
    except Exception as e:  # noqa
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})


# ---------- раздел «Блокировка»: ссылки, взятые в работу ----------
@app.get("/api/blocking-cases")
def list_blocking_cases():
    cases = storage.load_blocking_cases()
    shots = storage.load_screenshots()
    counts = {}
    for s in shots:
        counts[s["case_id"]] = counts.get(s["case_id"], 0) + 1
    for c in cases:
        c["screenshots_count"] = counts.get(c["id"], 0)
    return jsonify([_case_for_client(c) for c in cases])


def _case_for_client(case):
    """Дело в том виде, в каком его получает интерфейс: с готовым списком
    обращений (даже для старых дел, где он ещё не записан на диск) и
    вычисленным текущим состоянием — чтобы логика «последний этап решает»
    жила в одном месте (backend/appeals.py), а не дублировалась в JS."""
    if not case:
        return case
    out = dict(case)
    out["appeals"] = appeals_mod.get_appeals(case)
    out["current_decision"] = appeals_mod.current_decision(case)
    out["is_blocked"] = appeals_mod.is_blocked(case)
    out["appeal_failed"] = appeals_mod.last_attempt_failed(case)
    return out


@app.get("/api/chronic-domains")
def list_chronic_domains():
    """«Постоянно блокируемые ссылки» — авторы, у которых один и тот же
    базовый домен всплывает повторно под разными ссылками/поддоменами
    (см. backend/chronic_links.py). Порог и охват истории — константы
    в том модуле, не параметры запроса, чтобы у всех пользователей
    приложения было единое определение «постоянно блокируемого»."""
    return jsonify(chronic_links.compute_chronic_domains())


@app.post("/api/blocking-cases")
@require_role("editor")
def create_blocking_case():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Укажите ссылку"}), 400
    case = {
        "author_name": (data.get("author_name") or "").strip(),
        "work_title": (data.get("work_title") or "").strip(),
        "work_id": data.get("work_id"),
        "source": (data.get("source") or "").strip(),
        "title": (data.get("title") or "").strip() or url,
        "description": (data.get("description") or "").strip(),
        "url": url,
        "added_at": time.time(),
        # Дата обнаружения — раньше сотрудник должен был проставлять её
        # вручную при каждом добавлении ссылки, хотя по факту это почти
        # всегда «сегодня» (сама ссылка ведь добавляется в момент, когда
        # её нашли). Теперь подставляется автоматически сегодняшним
        # числом сервера — сотрудник может поправить дату вручную прямо в
        # таблице, если реально нашёл нарушение раньше, чем успел завести
        # дело (тот же принцип, что и у автоподстановки block_date ниже
        # по файлу — не жёсткая блокировка поля, а просто разумное
        # значение по умолчанию, которое не нужно трогать в обычном
        # случае).
        "discovered_at": (data.get("discovered_at") or "").strip() or time.strftime("%Y-%m-%d"),
        # Если вызывающий уже прислал эти поля вручную (не только автора и
        # ссылку) — не должны потеряться. Раньше их не было в словаре
        # вообще, из-за чего проверка «не перезаписывать вручную указанное»
        # ниже никогда не срабатывала ни для одного из трёх полей — баг
        # обнаружился при добавлении автозаполнения адреса, но касался
        # всех трёх с самого начала.
        "defendant": (data.get("defendant") or "").strip(),
        "defendant_email": (data.get("defendant_email") or "").strip(),
        "defendant_address": (data.get("defendant_address") or "").strip(),
    }
    # Пробуем сразу определить IP, хостинг-провайдера и email для жалоб.
    # Делается синхронно (одна ссылка — доли секунды на DNS, максимум пара
    # секунд на RDAP), но при любой ошибке сети просто оставляем поля
    # пустыми — создание дела никогда не должно падать из-за недоступности
    # внешнего сервиса.
    net = netinfo.lookup(url)
    if net.get("ip_address", ""):
        case["ip_address"] = net.get("ip_address", "")
    if net.get("hosting_org", "") and not case.get("defendant"):
        case["defendant"] = net.get("hosting_org", "")
    if net.get("defendant_email", "") and not case.get("defendant_email"):
        case["defendant_email"] = net.get("defendant_email", "")
    if net.get("defendant_address", "") and not case.get("defendant_address"):
        case["defendant_address"] = net.get("defendant_address", "")
    saved = storage.add_blocking_case(case)
    if saved is None:
        detail = "уже есть под этим же произведением" if case.get("work_id") else "уже есть в блокировке, но нельзя однозначно определить, под тем же произведением или нет (у одного из дел не указано произведение)"
        return jsonify({"error": f"Эта ссылка {detail}: {url}"}), 409
    _log("добавил в блокировку", f"{case['title']} ({url})")
    _maybe_auto_capture_chronic(saved)
    return jsonify(saved), 201


@app.post("/api/blocking-cases/<case_id>/lookup-ip")
@require_role("editor")
def lookup_blocking_case_ip(case_id):
    """Повторно определяет IP/хостинг/email для жалоб по ссылке дела и
    сохраняет в карточку (кнопка «🔄 обновить» в интерфейсе — на случай,
    если сайт сменил хостинг, или при создании определить не получилось)."""
    existing = storage.get_blocking_case(case_id)
    if not existing:
        return jsonify({"error": "Дело не найдено"}), 404
    net = netinfo.lookup(existing["url"])
    if not net.get("ip_address", ""):
        return jsonify({"error": "Не удалось определить IP-адрес по этой ссылке"}), 400
    patch = {"ip_address": net.get("ip_address", "")}
    if net.get("hosting_org", ""):
        patch["defendant"] = net.get("hosting_org", "")
    if net.get("defendant_email", ""):
        patch["defendant_email"] = net.get("defendant_email", "")
    if net.get("defendant_address", ""):
        patch["defendant_address"] = net.get("defendant_address", "")
    updated = storage.update_blocking_case(case_id, patch)
    _log("обновил IP/хостинг/email", f"{existing['title']}: {patch}")
    return jsonify(updated)


@app.get("/api/settings/complaint-template")
def get_complaint_template_endpoint():
    return jsonify(storage.get_complaint_template())


@app.put("/api/settings/complaint-template")
@require_role("editor")
def save_complaint_template_endpoint():
    data = request.get_json(force=True) or {}
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    if not subject or not body:
        return jsonify({"error": "Тема и текст не могут быть пустыми"}), 400
    if len(subject) > 300:
        return jsonify({"error": "Тема письма слишком длинная (максимум 300 символов)"}), 400
    if len(body) > 10000:
        return jsonify({"error": "Текст письма слишком длинный (максимум 10 000 символов)"}), 400
    storage.save_complaint_template(subject, body)
    _log("изменил шаблон текста жалобы", "")
    return jsonify(storage.get_complaint_template())


@app.delete("/api/settings/complaint-template")
@require_role("editor")
def reset_complaint_template_endpoint():
    storage.reset_complaint_template()
    _log("сбросил шаблон текста жалобы к значению по умолчанию", "")
    return jsonify(storage.get_complaint_template())


@app.get("/api/settings/templates/<name>")
def get_template_endpoint(name):
    if name not in storage.DEFAULT_TEMPLATES:
        return jsonify({"error": f"Неизвестный шаблон: {name}"}), 404
    return jsonify(storage.get_template(name))


@app.put("/api/settings/templates/<name>")
@require_role("editor")
def save_template_endpoint(name):
    if name not in storage.DEFAULT_TEMPLATES:
        return jsonify({"error": f"Неизвестный шаблон: {name}"}), 404
    data = request.get_json(force=True) or {}
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    if not subject or not body:
        return jsonify({"error": "Тема и текст не могут быть пустыми"}), 400
    if len(subject) > 300:
        return jsonify({"error": "Тема слишком длинная (максимум 300 символов)"}), 400
    if len(body) > 10000:
        return jsonify({"error": "Текст слишком длинный (максимум 10 000 символов)"}), 400
    storage.save_template(name, subject, body)
    _log(f"изменил шаблон «{name}»", "")
    return jsonify(storage.get_template(name))


@app.delete("/api/settings/templates/<name>")
@require_role("editor")
def reset_template_endpoint(name):
    if name not in storage.DEFAULT_TEMPLATES:
        return jsonify({"error": f"Неизвестный шаблон: {name}"}), 404
    storage.reset_template(name)
    _log(f"сбросил шаблон «{name}» к значению по умолчанию", "")
    return jsonify(storage.get_template(name))


# ---------- произвольные шаблоны (библиотека текста для площадок без автоотправки) ----------
@app.get("/api/custom-templates")
def list_custom_templates():
    return jsonify(storage.load_custom_templates())


@app.post("/api/custom-templates")
@require_role("editor")
def create_custom_template():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    if not name:
        return jsonify({"error": "Укажите название шаблона"}), 400
    if not body:
        return jsonify({"error": "Текст шаблона не может быть пустым"}), 400
    if len(name) > 100:
        return jsonify({"error": "Название слишком длинное (максимум 100 символов)"}), 400
    if len(body) > 10000:
        return jsonify({"error": "Текст слишком длинный (максимум 10 000 символов)"}), 400
    template = storage.create_custom_template(name, subject, body)
    _log("создал шаблон", name)
    return jsonify(template), 201


@app.put("/api/custom-templates/<template_id>")
@require_role("editor")
def update_custom_template(template_id):
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    if not name:
        return jsonify({"error": "Укажите название шаблона"}), 400
    if not body:
        return jsonify({"error": "Текст шаблона не может быть пустым"}), 400
    updated = storage.update_custom_template(template_id, name, subject, body)
    if not updated:
        return jsonify({"error": "Шаблон не найден"}), 404
    _log("изменил шаблон", name)
    return jsonify(updated)


@app.delete("/api/custom-templates/<template_id>")
@require_role("editor")
def delete_custom_template(template_id):
    if not storage.delete_custom_template(template_id):
        return jsonify({"error": "Шаблон не найден"}), 404
    _log("удалил шаблон", template_id)
    return jsonify({"ok": True})


@app.get("/api/settings/firm-letterhead")
@require_role("admin")
def get_firm_letterhead_endpoint():
    return jsonify(storage.get_firm_letterhead())


@app.put("/api/settings/firm-letterhead")
@require_role("admin")
def save_firm_letterhead_endpoint():
    data = request.get_json(force=True) or {}
    storage.save_firm_letterhead(data)
    _log("изменил реквизиты юрфирмы (шапка акта)", "")
    return jsonify(storage.get_firm_letterhead())


@app.get("/api/blocking-cases/<case_id>/complaint-email")
def get_complaint_email_draft(case_id):
    """Собирает готовые тему/текст/адресата жалобы — фронтенд открывает
    с этими данными окно создания письма в Gmail. Само письмо не
    отправляется сервером — только формируется черновик.

    Текст берётся из шаблона (по умолчанию — стандартный текст, либо
    сохранённый пользователем в «Настройки» → «Шаблон текста жалобы») —
    подставляются только данные конкретной ссылки ({url}, {author},
    {work_title}, {ip}), а весь остальной текст — ровно тот, что задан
    в шаблоне, одинаковый для всех писем, пока пользователь сам его
    не поменяет."""
    case = storage.get_blocking_case(case_id)
    if not case:
        return jsonify({"error": "Дело не найдено"}), 404

    template = storage.get_complaint_template()
    values = {
        "url": case.get("url", ""),
        "author": case.get("author_name") or "[автор]",
        "work_title": case.get("work_title") or case.get("title", ""),
        "ip": case.get("ip_address", ""),
    }
    subject = storage.render_complaint_template(template["subject"], values)
    body = storage.render_complaint_template(template["body"], values)

    return jsonify({
        "to": case.get("defendant_email", ""),
        "subject": subject,
        "body": body,
    })


@app.put("/api/blocking-cases/<case_id>")
@require_role("editor")
def update_blocking_case(case_id):
    existing = storage.get_blocking_case(case_id)
    if not existing:
        return jsonify({"error": "Дело не найдено"}), 404
    data = request.get_json(force=True)
    allowed = {"discovered_at", "claim_date", "claim_decision", "court_ruling_number", "court_ruling_date", "block_date", "appeals",
               "repeat_ruling", "rkn_number", "notes",
               "presence_google", "presence_yandex", "defendant", "ip_address",
               "defendant_email", "defendant_address", "petition_filed_at", "link_check_interval", "needs_resend",
               "rkn_filed_at", "first_appeal_decision", "repeat_appeal_decision",
               "repeat_petition_filed_at", "repeat_rkn_filed_at", "google_dmca_filed_at"}
    patch = {k: v for k, v in data.items() if k in allowed}
    for field in ("claim_decision", "first_appeal_decision", "repeat_appeal_decision"):
        if field in patch and patch[field] not in storage.APPEAL_DECISIONS:
            return jsonify({"error": f"Недопустимое значение поля «{field}». Разрешены: {storage.APPEAL_DECISIONS}"}), 400
    if "link_check_interval" in patch and patch["link_check_interval"] not in link_check.INTERVAL_SECONDS:
        return jsonify({"error": f"Недопустимый интервал. Разрешены: {list(link_check.INTERVAL_SECONDS)}"}), 400

    # Обращения в МГС/РКН — список appeals (см. backend/appeals.py). Старые
    # поля (court_ruling_number, rkn_number, first_appeal_decision ...)
    # остаются «зеркалом» списка, чтобы отчёты и выгрузки продолжали
    # работать. Если клиент прислал старые поля — переносим их в список.
    old_appeals = appeals_mod.get_appeals(existing)
    if "appeals" in patch:
        new_appeals, err = appeals_mod.validate_appeals(patch["appeals"])
        if err:
            return jsonify({"error": err}), 400
    else:
        new_appeals = appeals_mod.apply_legacy_patch(existing, patch)
    if new_appeals is not None:
        backup = appeals_mod.legacy_backup(existing)
        if backup:
            patch[appeals_mod.LEGACY_BACKUP_KEY] = backup  # оригинал старых полей — не теряется
        patch["appeals"] = new_appeals
        mirror = appeals_mod.legacy_mirror(new_appeals)
        # repeat_ruling, присланный старым клиентом как свободный текст,
        # не перезаписываем разобранной версией, если разбор ничего не дал
        patch.update(mirror)
    merged = {**existing, **patch}

    # Сброс «требуется повторная подача» — только когда это ДЕЙСТВИТЕЛЬНО
    # новая подача (новая дата в новом обращении или отметка о подаче
    # заявления), а не правка опечатки в уже стоявшей дате.
    new_filing = bool(
        data.get("petition_filed_at") or data.get("repeat_petition_filed_at")
        or data.get("rkn_filed_at") or data.get("repeat_rkn_filed_at")  # старый формат запроса
        or (new_appeals is not None and appeals_mod.new_dates_added(old_appeals, new_appeals))
    )
    if new_filing and existing.get("needs_resend"):
        patch["link_checked_at"] = ""
        patch["link_status"] = ""
        patch["needs_resend"] = False

    # Сотрудник вручную выбрал «заблокировано» — это подтверждение
    # блокировки. Раньше флаг needs_resend (выставленный проверкой, когда
    # ссылка «ожила») при этом не снимался, и дело навсегда застревало в
    # активной «Блокировке»: автоархивация ждала снятия флага, а флаг
    # снимался только новой датой подачи.
    # Подтверждением считается только НОВЫЙ выбор «заблокировано» (было
    # другое значение — стало «заблокировано»). Добавление пустого блока
    # «повторное обращение» или правка других полей подтверждением не
    # является — иначе кнопка «+ Повторное обращение» у дела с ожившей
    # ссылкой сразу отправляла бы его в архив.
    newly_blocked = (
        patch.get("claim_decision") == "заблокировано" and existing.get("claim_decision") != "заблокировано"
    ) or (new_appeals is not None and any(
        a["decision"] == "заблокировано" and (i >= len(old_appeals) or old_appeals[i]["decision"] != "заблокировано")
        for i, a in enumerate(new_appeals)
    ))
    now_blocked = link_check.is_blocked(merged)
    if now_blocked and newly_blocked:
        patch["needs_resend"] = False
        patch["link_status"] = ""
        patch["link_checked_at"] = ""
        if not patch.get("block_date"):
            # новая блокировка (в т.ч. повторная после «ожившей» ссылки) —
            # отсчёт мониторинга начинается заново с сегодняшнего дня
            patch["block_date"] = time.strftime("%Y-%m-%d")

    # Дата блокировки — «якорная» точка отсчёта для фонового мониторинга
    # (см. link_check._anchor_date): без неё дело, ушедшее в архив после
    # «заблокировано», больше никогда не проверяется.
    if now_blocked and not (patch.get("block_date") or existing.get("block_date")):
        patch["block_date"] = time.strftime("%Y-%m-%d")

    # Журнал отправок (только для admin, см. «Администрирование» → «Журнал
    # отправок») — фиксируем момент, когда одно из этих полей меняется на
    # НЕПУСТОЕ значение, ОТЛИЧНОЕ от того, что было раньше. Это покрывает
    # и первую отправку (пусто → дата), и повторную — раньше проверялось
    # только «было пусто», и повторные отправки полей без отдельного
    # «повторного» поля-двойника (claim_date, google_dmca_filed_at — в
    # отличие от petition_filed_at, у которого есть repeat_petition_filed_at)
    # в журнал не попадали вообще. Запись с тем же самым значением, что уже
    # стояло (просто повторно отправили тот же PUT без реального
    # изменения), не логируется — это не событие.
    # «Другое» (и Avito как один из его пунктов) сюда не входит — у него
    # свой список записей и свои эндпоинты (см. add_other_complaint ниже),
    # не плоское поле в PATCH.
    for field in ("claim_date", "petition_filed_at", "repeat_petition_filed_at",
                  "rkn_filed_at", "repeat_rkn_filed_at", "google_dmca_filed_at"):
        if patch.get(field) and patch.get(field) != existing.get(field):
            log_type = {
                "claim_date": "claim", "petition_filed_at": "petition",
                "repeat_petition_filed_at": "repeat_petition", "rkn_filed_at": "rkn",
                "repeat_rkn_filed_at": "repeat_rkn", "google_dmca_filed_at": "google_dmca",
            }[field]
            storage.add_complaint_send_log_entry({
                "username": session.get("username", ""),
                "type": log_type,
                "case_id": case_id,
                "url": existing.get("url", ""),
                "author_name": existing.get("author_name", ""),
                "work_title": existing.get("work_title") or existing.get("title", ""),
                "date_value": patch[field],
                "channel": "",
            })

    updated = storage.update_blocking_case(case_id, patch)
    if patch:
        field_summary = ", ".join(f"{k}={v}" for k, v in patch.items())
        _log("изменил дело блокировки", f"{existing['title']}: {field_summary}")

    # Как только дело становится по-настоящему «закрытым» — сразу
    # переносим его в архив отчётов, не дожидаясь конца месяца и ручной
    # кнопки «Завершить месяц и заархивировать» (см. заметку разработки,
    # 01.09). "auto_archived" в ответе — сигнал фронтенду сразу убрать
    # строку из таблицы «Блокировка», не дожидаясь полной перезагрузки
    # списка с сервера.
    if _maybe_auto_archive_blocked_case(updated):
        result = _case_for_client(updated)
        result["auto_archived"] = True
        return jsonify(result)

    return jsonify(_case_for_client(updated))


def _maybe_auto_archive_blocked_case(case):
    """Как только дело становится по-настоящему «закрытым» (заблокировано
    на любом из трёх этапов И проверка ссылки не требует повторной
    подачи) — сразу переносим его в архив отчётов, не дожидаясь конца
    месяца и ручной кнопки «Завершить месяц и заархивировать». Период
    определяется персональным днём начала отчётного периода автора
    (report_period_start_day, по умолчанию 1 — обычный календарный
    месяц, поведение не меняется для тех авторов, у кого этот день не
    задан явно). Возвращает True, если дело было заархивировано."""
    if not link_check.is_blocked(case) or case.get("needs_resend"):
        return False
    author = next((a for a in storage.load_authors() if a["name"] == case.get("author_name")), None)
    start_day = (author or {}).get("report_period_start_day", 1)
    year, month = reports.resolve_report_period(start_day)
    storage.archive_reported_cases([case], year, month)
    storage.log_action(
        "система (авто)",
        "автоматически перенёс заблокированное дело в архив отчётов",
        f"{case.get('title', '')} ({case.get('url', '')}) — период {year:04d}-{month:02d}",
    )
    return True


@app.post("/api/blocking-cases/<case_id>/confirm-blocked")
@require_role("editor")
def confirm_blocked(case_id):
    """«Ложная тревога — ссылка заблокирована». Проверка решила, что
    ссылка снова открывается, но сотрудник видит, что это не так (открылась
    заглушка провайдера, проверка шла с зарубежного сервера и т.п.).
    Снимаем тревогу, запоминаем отпечаток ответа сайта — чтобы тот же
    самый ответ больше не возвращал дело из архива — и архивируем."""
    case = storage.get_blocking_case(case_id)
    if not case:
        return jsonify({"error": "Дело не найдено"}), 404
    if not link_check.is_blocked(case):
        return jsonify({"error": "У последнего этапа дела нет статуса «заблокировано» — сначала выберите его"}), 400
    details = case.get("link_check_details") or {}
    patch = {"needs_resend": False, "link_status": "недоступна"}
    if details.get("signature"):
        patch["false_alarm_signature"] = details["signature"]
    if not case.get("block_date"):
        patch["block_date"] = time.strftime("%Y-%m-%d")
    updated = storage.update_blocking_case(case_id, patch)
    _log("подтвердил блокировку (ложная тревога проверки)", f"{case.get('title', '')} ({case.get('url', '')})")
    result = _case_for_client(updated)
    result["auto_archived"] = _maybe_auto_archive_blocked_case(updated)
    return jsonify(result)


@app.post("/api/blocking-cases/<case_id>/other-complaints")
@require_role("editor")
def add_other_complaint(case_id):
    """Добавляет одну запись в список «Другое» — обращений может быть
    сколько угодно на одно дело (например, отдельно VK, отдельно Meta,
    отдельно торрент-трекер), а не одна запись, как было раньше."""
    case = storage.get_blocking_case(case_id)
    if not case:
        return jsonify({"error": "Дело не найдено"}), 404
    data = request.get_json(force=True) or {}
    filed_at = (data.get("filed_at") or "").strip()
    method = (data.get("method") or "").strip()
    notes = (data.get("notes") or "").strip()
    if not filed_at or not method:
        return jsonify({"error": "Укажите и дату, и способ/куда отправлено"}), 400
    entry = {
        "id": str(uuid.uuid4())[:8],
        "filed_at": filed_at,
        "method": method,
        "notes": notes,
    }
    resolved_at = (data.get("resolved_at") or "").strip()
    if resolved_at:
        entry["resolved_at"] = resolved_at  # дата удаления ссылки площадкой (для отчёта, лист Google)
    updated = storage.add_other_complaint_entry(case_id, entry)
    storage.add_complaint_send_log_entry({
        "username": session.get("username", ""),
        "type": "other",
        "case_id": case_id,
        "url": case.get("url", ""),
        "author_name": case.get("author_name", ""),
        "work_title": case.get("work_title") or case.get("title", ""),
        "date_value": filed_at,
        "channel": method,
    })
    _log("добавил обращение «Другое»", f"{case['title']}: {method} ({filed_at})")
    return jsonify(updated), 201


@app.delete("/api/blocking-cases/<case_id>/other-complaints/<entry_id>")
@require_role("editor")
def remove_other_complaint(case_id, entry_id):
    case = storage.get_blocking_case(case_id)
    if not case:
        return jsonify({"error": "Дело не найдено"}), 404
    updated = storage.delete_other_complaint_entry(case_id, entry_id)
    if updated is None:
        return jsonify({"error": "Запись не найдена"}), 404
    _log("удалил обращение «Другое»", case["title"])
    return jsonify(updated)


@app.delete("/api/blocking-cases/<case_id>")
@require_role("editor")
def remove_blocking_case(case_id):
    existing = storage.get_blocking_case(case_id)
    storage.delete_blocking_case(case_id)  # каскадно удалит и скриншоты
    _log("удалил дело блокировки", existing["title"] if existing else case_id)
    return jsonify({"ok": True})


# ---------- скриншоты по делу блокировки (фиксация нарушения) ----------
ALLOWED_SCREENSHOT_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "pdf"}


@app.get("/api/blocking-cases/<case_id>/screenshots")
def list_case_screenshots(case_id):
    if not storage.get_blocking_case(case_id):
        return jsonify({"error": "Дело не найдено"}), 404
    return jsonify(storage.get_case_screenshots(case_id))


@app.post("/api/blocking-cases/<case_id>/screenshots/capture")
@require_role("editor")
def start_capture_case_screenshot(case_id):
    """Раньше делало снимок синхронно (до 20 секунд внутри одного HTTP-
    запроса) — на сервере с одним рабочим процессом (gunicorn -w 1, см.
    заметки к развёртыванию) это на всё это время блокировало ответ сервера
    для всех остальных пользователей. Теперь запускает фоновую задачу и
    сразу отвечает — фронтенд опрашивает статус отдельным запросом."""
    case = storage.get_blocking_case(case_id)
    if not case:
        return jsonify({"error": "Дело не найдено"}), 404
    job_id = jobs.start_screenshot_job(case["url"])
    return jsonify({"job_id": job_id}), 202


@app.get("/api/blocking-cases/<case_id>/screenshots/capture/<job_id>")
def poll_capture_case_screenshot(case_id, job_id):
    job = jobs.get_screenshot_job(job_id)
    if not job:
        return jsonify({"error": "Задача не найдена"}), 404
    if job["status"] in ("queued", "running"):
        return jsonify({"status": job["status"]})
    if job["status"] == "error":
        return jsonify({"status": "error", "error": job["error"]})

    # status == "done" — файл и метаданные сохраняем здесь (не в фоновом
    # потоке), потому что тут, в обычном HTTP-запросе, есть доступ к сессии
    # для журнала действий. Сохраняем только один раз, даже если статус
    # опросят повторно.
    if job.get("saved_meta"):
        return jsonify({"status": "done", "screenshot": job["saved_meta"]})

    case = storage.get_blocking_case(case_id)
    if not case:
        return jsonify({"error": "Дело не найдено"}), 404
    result = job["result"]
    meta = _save_violation_screenshot(case_id, result)
    job["saved_meta"] = meta
    storage.log_action(session.get("username"), "сделал автоматический скриншот", f"{case['title']} ({case['url']})")
    return jsonify({"status": "done", "screenshot": meta})


def _save_violation_screenshot(case_id, result, username=None):
    """Общая логика сохранения скриншота самого нарушения — используется
    и обычным опросом задачи (см. выше), и автоматическим запуском при
    обнаружении «постоянно блокируемого» домена (см.
    _maybe_auto_capture_chronic ниже) — там нет активного HTTP-запроса,
    поэтому вынесено в отдельную функцию, не завязанную на request/session.

    Плашка с датой фиксации (московское время, MSK/UTC+3) впечатывается
    прямо в сам файл скриншота — так же, как уже делалось для снимка
    подтверждения хостинга (см. capture-defendant-proof ниже)."""
    stamped_png = image_stamp.stamp_banner(
        result["png_bytes"],
        fields=[("Ссылка на странице нарушения", result["captured_url"])],
        captured_at=result["captured_at"],
    )

    base_name = f"{uuid.uuid4().hex[:12]}_auto"
    png_filename = f"{base_name}.png"
    html_filename = f"{base_name}.html"

    os.makedirs(storage.SCREENSHOTS_DIR, exist_ok=True)
    png_path = os.path.join(storage.SCREENSHOTS_DIR, png_filename)
    with open(png_path, "wb") as f:
        f.write(stamped_png)
    html_path = os.path.join(storage.SCREENSHOTS_DIR, html_filename)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(result["html"])

    # Страница открылась (иначе screenshot_capture.capture уже бросил бы
    # исключение раньше, до вызова этой функции), но похожа на антибот-
    # проверку/капчу, а не на реальный контент нарушения — раньше такие
    # снимки тихо сохранялись как обычные, без какой-либо пометки (см.
    # заметку разработки, 03.09). Само сохранение не блокируем — снимок
    # капчи тоже полезен как факт (сайт жив, но защищён), просто явно
    # предупреждаем, чтобы не приняли его по ошибке за снимок нарушения.
    description = "Автоматический снимок"
    if screenshot_capture.looks_like_bot_wall(result.get("html")):
        description += " · ⚠️ похоже на антибот-проверку/капчу — возможно, это не сам пиратский контент, а страница-заглушка"

    return storage.add_screenshot({
        "case_id": case_id,
        "original_name": f"screenshot_{time.strftime('%Y-%m-%d_%H-%M', time.localtime(result['captured_at']))}.png",
        "stored_filename": png_filename,
        "description": description,
        "size": os.path.getsize(png_path),
        "uploaded_at": result["captured_at"],
        "source": "auto",
        "captured_at": result["captured_at"],
        "captured_url": result["captured_url"],
        "html_filename": html_filename,
        "purpose": "violation",  # автоскриншот всегда фиксирует сам пиратский контент, не подтверждение хостинга
    })


# 2ip.io — русскоязычный публичный whois-сервис (тот, которым вы уже
# проверяли вручную) — результат появляется только после заполнения формы
# и нажатия кнопки, прямой ссылки с готовым результатом по IP нет. Из-за
# этого автоматизация чуть более хрупкая, чем через открытый RDAP-запрос:
# несколько вариантов селекторов — попытка сделать её устойчивее к мелким
# изменениям разметки сайта, но полной гарантии дать нельзя, это чужой
# сайт, а не открытый протокол.
_2IP_FORM_URL = "https://2ip.io/"
_2IP_INPUT_SELECTORS = [
    'input[name="ip"]',
    'input[type="text"]',
    'form input:visible',
]
_2IP_SUBMIT_SELECTORS = [
    'button:has-text("Проверить")',
    'input[type="submit"]',
    'button[type="submit"]',
]


# job_id -> {"domain", "ip", "defendant", "source_label"} — контекст для
# плашки, которую печатаем на изображении при сохранении результата (см.
# image_stamp.py). Отдельный словарь, не внутри jobs.py — это данные,
# нужные только этому конкретному эндпоинту, не общая часть механизма
# фоновых задач.
_defendant_proof_context = {}


@app.post("/api/blocking-cases/<case_id>/screenshots/capture-defendant-proof")
@require_role("editor")
def start_capture_defendant_proof_screenshot(case_id):
    """Автоматический скриншот русскоязычного whois-сервиса (2ip.io) с
    впечатанной прямо в картинку плашкой: домен, IP, ответчик, источник,
    точная дата и время фиксации — одним взглядом, без необходимости
    искать эти данные по разным полям базы или в отдельной метке времени.

    Если заполнить форму 2ip.io не удалось (сайт поменял разметку,
    недоступен и т.п.) — запасной вариант больше не сырой JSON с rdap.org
    на английском (как было раньше), а собственная читаемая страница на
    русском, построенная из тех же данных, что уже определены и лежат в
    самом деле («Ответчик», «Email ответчика») — без повторного похода
    в сеть, и без риска зависнуть на чужой странице."""
    case = storage.get_blocking_case(case_id)
    if not case:
        return jsonify({"error": "Дело не найдено"}), 404
    ip = (case.get("ip_address") or "").strip()
    if not ip or ip == "0.0.0.0":
        return jsonify({"error": "Сначала определите IP-адрес дела (кнопка 🔄 рядом с полем IP-адрес) — снимок без него бессмыслен"}), 400

    # Пробуем русскоязычный источник первым (заполнение формы — более
    # хрупкая автоматизация, сайт не наш, может в любой момент поменять
    # разметку). Если не получилось — откатываемся на собственную читаемую
    # страницу-сводку (см. netinfo.render_readable_rdap_summary_html) —
    # тоже на русском, без зависимости от чужого сайта. context — общий
    # изменяемый словарь между этой функцией и фоновым потоком: label
    # обновится на «запасной вариант», если реально пришлось откатиться.
    context = {"source_label": "2ip.io", "defendant_check": None}

    def capture_fn():
        # Сверка «Ответчика» с тем, что по этому IP реально показывает
        # RDAP — ловит случай, когда IP в деле сменился (сайт переехал на
        # другой хостинг), а поле «Ответчик» осталось от старого
        # хостинга: тогда скриншот-подтверждение будет фактически не про
        # того ответчика. Внутри фоновой функции, не в самом HTTP-запросе —
        # RDAP-запрос может занять несколько секунд, а этот эндпоинт и
        # так уже вынесен в фон именно чтобы не задерживать ответ сервера
        # (см. комментарий про gunicorn -w 1 выше по функции).
        context["defendant_check"] = netinfo.check_defendant_matches_ip(ip, case.get("defendant", ""))
        try:
            return screenshot_capture.capture_with_form_query(
                _2IP_FORM_URL, ip, _2IP_INPUT_SELECTORS, _2IP_SUBMIT_SELECTORS,
            )
        except screenshot_capture.ScreenshotCaptureError:
            context["source_label"] = "данные RDAP (запасной вариант — 2ip.io не сработал)"
            summary_html = netinfo.render_readable_rdap_summary_html(
                ip, case.get("defendant", ""), case.get("defendant_email", ""),
                domain=netinfo._extract_domain(case.get("url", "")),
            )
            data_url = "data:text/html;charset=utf-8;base64," + base64.b64encode(summary_html.encode("utf-8")).decode()
            return screenshot_capture.capture(data_url)

    job_id = jobs.start_screenshot_job_custom(capture_fn)
    _defendant_proof_context[job_id] = {
        "domain": netinfo._extract_domain(case.get("url", "")),
        "ip": ip,
        "defendant": case.get("defendant", ""),
        "_source_label_ref": context,
    }
    return jsonify({"job_id": job_id}), 202


@app.get("/api/blocking-cases/<case_id>/screenshots/capture-defendant-proof/<job_id>")
def poll_capture_defendant_proof_screenshot(case_id, job_id):
    job = jobs.get_screenshot_job(job_id)
    if not job:
        return jsonify({"error": "Задача не найдена"}), 404
    if job["status"] in ("queued", "running"):
        return jsonify({"status": job["status"]})
    if job["status"] == "error":
        _defendant_proof_context.pop(job_id, None)
        return jsonify({"status": "error", "error": job["error"]})

    if job.get("saved_meta"):
        return jsonify({"status": "done", "screenshot": job["saved_meta"]})

    case = storage.get_blocking_case(case_id)
    if not case:
        return jsonify({"error": "Дело не найдено"}), 404
    result = job["result"]
    ctx = _defendant_proof_context.pop(job_id, {})
    source_label = ctx.get("_source_label_ref", {}).get("source_label", "2ip.io")
    defendant_check = ctx.get("_source_label_ref", {}).get("defendant_check") or {"checked": False, "matches": True, "rdap_org": None}

    meta = _save_defendant_proof_screenshot(case_id, case, result, ctx, source_label, defendant_check)
    job["saved_meta"] = meta
    storage.log_action(session.get("username"), "сделал автоматический скриншот подтверждения хостинга", f"{case['title']} (IP: {case.get('ip_address', '')})")
    return jsonify({"status": "done", "screenshot": meta, "defendant_check": defendant_check})


def _save_defendant_proof_screenshot(case_id, case, result, ctx, source_label, defendant_check):
    """Общая логика сохранения скриншота подтверждения хостинга/IP — см.
    комментарий у _save_violation_screenshot выше, тот же принцип
    разделения на переиспользуемую функцию без завязки на HTTP-запрос."""
    stamped_png = image_stamp.stamp_banner(
        result["png_bytes"],
        fields=[
            ("Домен", ctx.get("domain", "")),
            ("IP-адрес", ctx.get("ip", case.get("ip_address", ""))),
            ("Ответчик", ctx.get("defendant", case.get("defendant", ""))),
            ("Источник", source_label),
        ],
        captured_at=result["captured_at"],
    )

    base_name = f"{uuid.uuid4().hex[:12]}_whois"
    png_filename = f"{base_name}.png"
    html_filename = f"{base_name}.html"

    os.makedirs(storage.SCREENSHOTS_DIR, exist_ok=True)
    png_path = os.path.join(storage.SCREENSHOTS_DIR, png_filename)
    with open(png_path, "wb") as f:
        f.write(stamped_png)
    html_path = os.path.join(storage.SCREENSHOTS_DIR, html_filename)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(result["html"])

    # defendant_check не совпало — не блокируем сохранение скриншота (он
    # всё равно полезен как факт фиксации), но пишем расхождение прямо в
    # описание снимка, чтобы оно осталось видно и позже, не только в
    # момент создания (всплывающее предупреждение фронтенд покажет один
    # раз сразу после съёмки — см. defendant_check в ответе ниже).
    description = f"Автоматический снимок ({source_label}) — домен, IP и ответчик впечатаны на изображении"
    if defendant_check.get("checked") and not defendant_check.get("matches"):
        description += f" · ⚠️ по данным RDAP этот IP принадлежит «{defendant_check.get('rdap_org')}», не «{ctx.get('defendant', case.get('defendant', ''))}»"
    if screenshot_capture.looks_like_bot_wall(result.get("html")):
        description += " · ⚠️ похоже на антибот-проверку/капчу, не на реальный результат whois-сервиса"

    return storage.add_screenshot({
        "case_id": case_id,
        "original_name": f"whois_{time.strftime('%Y-%m-%d_%H-%M', time.localtime(result['captured_at']))}.png",
        "stored_filename": png_filename,
        "description": description,
        "size": os.path.getsize(png_path),
        "uploaded_at": result["captured_at"],
        "source": "auto",
        "captured_at": result["captured_at"],
        "captured_url": result["captured_url"],
        "html_filename": html_filename,
        "purpose": "defendant_proof",
    })


def _maybe_auto_capture_chronic(case):
    """Проверяет, стал ли (автор, базовый домен) этого дела «постоянно
    блокируемым» после его добавления — если да, добавляет домен в
    справочник «Поиск по сайтам» (см. ниже).

    Раньше на этом же шаге ЕЩЁ запускалась автоматическая съёмка
    скриншота нарушения и подтверждения хостинга/IP в фоне для всех
    подходящих дел группы (headless Chromium, без участия пользователя).
    ОТКЛЮЧЕНО 16.09.2026 по прямой просьбе — именно этот автоматический
    запуск браузера, срабатывающий незаметно для сотрудника при каждом
    новом повторе домена, оказался главной причиной падений сервера и
    100%-й загрузки на минимальной VM (см. также комментарий у
    _CHROMIUM_CONCURRENCY в jobs.py про инцидент 28.08.2026 — тот
    инцидент тоже был про скриншоты, просто ещё и с параллельным
    запуском). Скрытие раздела «Скриншоты» в интерфейсе (см.
    frontend/styles.css) само по себе не останавливало эту автоматику,
    т.к. она вызывается не из кнопки, а прямо отсюда — из
    create_blocking_case. Сама функция _auto_capture_case_screenshots и
    ручные кнопки/эндпоинты скриншотов никуда не делись и продолжают
    работать как раньше — отключён только этот автоматический триггер.
    Чтобы вернуть — раскомментировать блок ниже."""
    count, domain = chronic_links.count_domain_occurrences(case.get("author_name", ""), case.get("work_title", ""), case.get("url", ""))
    if count < chronic_links.CHRONIC_THRESHOLD:
        return

    # for sibling in chronic_links.active_cases_for_domain(case.get("author_name", ""), case.get("work_title", ""), domain):
    #     if storage.get_case_screenshots(sibling["id"]):
    #         continue  # уже есть хоть один скриншот — не дублируем
    #     threading.Thread(target=_auto_capture_case_screenshots, args=(sibling, domain), daemon=True).start()

    _maybe_add_chronic_domain_to_site_directory(case.get("author_name", ""), domain)


def _maybe_add_chronic_domain_to_site_directory(author_name, domain):
    """При обнаружении «постоянно блокируемого» домена добавляет его в
    справочник «Поиск по сайтам» (см. backend/site_search.py) — раз домен
    уже дважды всплыл под новыми ссылками у одного автора, есть смысл
    проверять его напрямую при каждом поиске, а не полагаться только на
    случайное попадание в выдачу Яндекса/Google.

    Справочник сайтов общий на всё приложение, не привязан к автору — если
    домен там уже есть (под любым поддоменом с тем же базовым доменом),
    ничего не делаем, дублей не создаём. type="auto" — тот же режим по
    умолчанию, что и при добавлении сайта вручную через раздел «Поиск по
    сайтам», сам разбирается, обычная это ссылка или форум на движке
    XenForo."""
    existing_domains = set()
    for s in storage.load_sites():
        try:
            host = site_search._configured_domain(s)
        except Exception:  # noqa — битый url_template в справочнике не должен ронять создание дела
            continue
        if host:
            existing_domains.add(chronic_links._base_domain(host))
    if domain in existing_domains:
        return
    storage.upsert_site({
        "id": None,
        "name": f"{domain} (постоянно блокируемый — {author_name})",
        "url_template": f"https://{domain}",
        "type": "auto",
    })
    storage.log_action("система (авто)", "добавил домен в справочник «Поиск по сайтам» — постоянно блокируемый", f"{domain} (автор: {author_name})")


def _auto_capture_case_screenshots(case, domain):
    """Съёмка нарушения + подтверждения хостинга/IP для ОДНОГО дела, в
    фоновом потоке — вызывается для каждого подходящего дела из
    _maybe_auto_capture_chronic (там же и объяснение, зачем перебирать
    всю группу, а не только новое дело)."""
    case_id = case["id"]

    # Нарушение — просто открыть саму страницу и снять.
    try:
        with jobs._chromium_semaphore:
            result = screenshot_capture.capture(case["url"])
        _save_violation_screenshot(case_id, result)
        storage.log_action("система (авто)", "автоматический скриншот нарушения — постоянно блокируемый домен", f"{case.get('title', '')} ({case['url']}, домен: {domain})")
    except Exception:  # noqa — авто-функция никогда не должна ронять поток сервера
        pass

    # Подтверждение хостинга/IP — только если IP вообще определён,
    # иначе снимок был бы бессмысленным (тот же принцип, что и в
    # ручной кнопке "📋" — см. start_capture_defendant_proof_screenshot).
    ip = (case.get("ip_address") or "").strip()
    if not ip or ip == "0.0.0.0":
        return
    try:
        defendant_check = netinfo.check_defendant_matches_ip(ip, case.get("defendant", ""))
        source_label = "2ip.io"
        try:
            with jobs._chromium_semaphore:
                result2 = screenshot_capture.capture_with_form_query(
                    _2IP_FORM_URL, ip, _2IP_INPUT_SELECTORS, _2IP_SUBMIT_SELECTORS,
                )
        except screenshot_capture.ScreenshotCaptureError:
            source_label = "данные RDAP (запасной вариант — 2ip.io не сработал)"
            summary_html = netinfo.render_readable_rdap_summary_html(
                ip, case.get("defendant", ""), case.get("defendant_email", ""),
                domain=netinfo._extract_domain(case.get("url", "")),
            )
            data_url = "data:text/html;charset=utf-8;base64," + base64.b64encode(summary_html.encode("utf-8")).decode()
            with jobs._chromium_semaphore:
                result2 = screenshot_capture.capture(data_url)
        ctx = {"domain": netinfo._extract_domain(case.get("url", "")), "ip": ip, "defendant": case.get("defendant", "")}
        fresh_case = storage.get_blocking_case(case_id) or case
        _save_defendant_proof_screenshot(case_id, fresh_case, result2, ctx, source_label, defendant_check)
        storage.log_action("система (авто)", "автоматический скриншот подтверждения хостинга — постоянно блокируемый домен", f"{case.get('title', '')} (IP: {ip}, домен: {domain})")
    except Exception:  # noqa
        pass


@app.get("/api/blocking-cases/<case_id>/screenshots/<shot_id>/html")
def download_case_screenshot_html(case_id, shot_id):
    """HTML-снимок страницы на момент автоматического скриншота — отдельное
    доказательство содержимого страницы, независимое от самой картинки."""
    shot = storage.get_screenshot(shot_id)
    if not shot or shot["case_id"] != case_id or not shot.get("html_filename"):
        return jsonify({"error": "HTML-снимок не найден"}), 404
    path = os.path.join(storage.SCREENSHOTS_DIR, shot["html_filename"])
    if not os.path.exists(path):
        return jsonify({"error": "Файл отсутствует на диске"}), 404
    return send_file(path, as_attachment=True, download_name=f"{shot['stored_filename']}.html")


@app.post("/api/blocking-cases/<case_id>/screenshots")
@require_role("editor")
def upload_case_screenshot(case_id):
    if not storage.get_blocking_case(case_id):
        return jsonify({"error": "Дело не найдено"}), 404
    if "file" not in request.files:
        return jsonify({"error": "Файл не передан"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Файл не выбран"}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_SCREENSHOT_EXTENSIONS:
        return jsonify({"error": f"Недопустимый тип файла .{ext}. Разрешены: {', '.join(sorted(ALLOWED_SCREENSHOT_EXTENSIONS))}"}), 400

    description = (request.form.get("description") or "").strip()
    purpose = (request.form.get("purpose") or "violation").strip()
    if purpose not in ("violation", "defendant_proof"):
        purpose = "violation"

    original_name = secure_filename(file.filename) or f"file.{ext}"
    stored_filename = f"{uuid.uuid4().hex[:12]}_{original_name}"
    os.makedirs(storage.SCREENSHOTS_DIR, exist_ok=True)
    save_path = os.path.join(storage.SCREENSHOTS_DIR, stored_filename)
    file.save(save_path)
    size = os.path.getsize(save_path)

    meta = storage.add_screenshot({
        "case_id": case_id,
        "original_name": file.filename,
        "stored_filename": stored_filename,
        "description": description,
        "size": size,
        "uploaded_at": time.time(),
        "purpose": purpose,
    })
    case = storage.get_blocking_case(case_id)
    _log("загрузил скриншот", f"{file.filename} (дело: {case['title'] if case else case_id})")
    return jsonify(meta), 201


@app.get("/api/blocking-cases/<case_id>/screenshots/<shot_id>/file")
def view_case_screenshot(case_id, shot_id):
    shot = storage.get_screenshot(shot_id)
    if not shot or shot["case_id"] != case_id:
        return jsonify({"error": "Скриншот не найден"}), 404
    path = os.path.join(storage.SCREENSHOTS_DIR, shot["stored_filename"])
    if not os.path.exists(path):
        return jsonify({"error": "Файл отсутствует на диске"}), 404
    return send_file(path)  # без as_attachment — чтобы показывалось прямо в браузере/как превью


@app.get("/api/blocking-cases/<case_id>/screenshots/<shot_id>/download")
def download_case_screenshot(case_id, shot_id):
    shot = storage.get_screenshot(shot_id)
    if not shot or shot["case_id"] != case_id:
        return jsonify({"error": "Скриншот не найден"}), 404
    path = os.path.join(storage.SCREENSHOTS_DIR, shot["stored_filename"])
    if not os.path.exists(path):
        return jsonify({"error": "Файл отсутствует на диске"}), 404
    return send_file(path, as_attachment=True, download_name=shot["original_name"])


@app.delete("/api/blocking-cases/<case_id>/screenshots/<shot_id>")
@require_role("editor")
def delete_case_screenshot(case_id, shot_id):
    shot = storage.get_screenshot(shot_id)
    if not shot or shot["case_id"] != case_id:
        return jsonify({"error": "Скриншот не найден"}), 404
    storage.delete_screenshot(shot_id)
    _log("удалил скриншот", shot["original_name"])
    return jsonify({"ok": True})


@app.get("/api/blocking-cases/export.csv")
def export_blocking_cases_csv():
    cases = [c for c in storage.load_blocking_cases() if link_check.is_blocked(c)]
    csv_text = exporters.blocking_cases_to_csv(cases)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=blokirovka.csv"},
    )


@app.get("/api/blocking-cases/monthly-report")
def monthly_blocking_report():
    """Просто скачать отчёт — ничего не меняет и не архивирует. Можно
    смотреть сколько угодно раз, в том числе просто чтобы свериться."""
    month_param = request.args.get("month")  # формат YYYY-MM
    if not month_param or "-" not in month_param:
        return jsonify({"error": "Укажите месяц в формате ?month=YYYY-MM"}), 400
    try:
        year_s, month_s = month_param.split("-")
        year, month = int(year_s), int(month_s)
        if not (1 <= month <= 12):
            raise ValueError
    except ValueError:
        return jsonify({"error": "Неверный формат месяца, ожидается YYYY-MM"}), 400

    cases = storage.load_blocking_cases()
    xlsx_bytes = reports.build_monthly_report(cases, year, month)
    filename = f"otchet_blokirovka_{year:04d}-{month:02d}.xlsx"
    return Response(
        xlsx_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.patch("/api/blocking-cases/<case_id>/other-complaints/<entry_id>")
@require_role("editor")
def update_other_complaint(case_id, entry_id):
    """Отметить у жалобы дату удаления ссылки площадкой (например, Google
    убрал ссылку из выдачи) — попадает в лист «Поисковая выдача Google»."""
    data = request.get_json(force=True) or {}
    resolved_at = (data.get("resolved_at") or "").strip()
    if resolved_at and not re.match(r"^\d{4}-\d{2}-\d{2}$", resolved_at):
        return jsonify({"error": "Дата должна быть в формате ГГГГ-ММ-ДД"}), 400
    updated = storage.update_other_complaint_entry(case_id, entry_id, {"resolved_at": resolved_at})
    if not updated:
        return jsonify({"error": "Запись не найдена"}), 404
    return jsonify(updated)


def _norm_title(text):
    return re.sub(r"[«»\"'“”„\s]+", " ", (text or "")).strip().lower()


@app.get("/api/reports/protection.xlsx")
@require_role("admin")
def download_protection_report():
    """Отчёт для заказчика по образцу юрфирмы за любой период «с … по …».
    Параметры: date_from, date_to (ГГГГ-ММ-ДД, обязательны); author_id и
    work_id — необязательны: без них — все авторы, с author_id — один
    автор со всеми произведениями, с work_id — одно произведение.
    Дела берутся и из «Блокировки», и из архива (заблокированные дела
    уходят в архив сразу — раньше из-за этого они пропадали из отчёта)."""
    date_from = (request.args.get("date_from") or "").strip()
    date_to = (request.args.get("date_to") or "").strip()
    try:
        d1 = time.strptime(date_from, "%Y-%m-%d")
        d2 = time.strptime(date_to, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Укажите период: date_from и date_to в формате ГГГГ-ММ-ДД"}), 400
    if d1 > d2:
        return jsonify({"error": "Дата начала периода позже даты окончания"}), 400
    author_id = (request.args.get("author_id") or "").strip()
    work_id = (request.args.get("work_id") or "").strip()
    # несколько произведений (в т.ч. у разных авторов): work_ids=id1,id2,…
    selected_ids = [w for w in (request.args.get("work_ids") or "").split(",") if w.strip()]
    if work_id:
        selected_ids.append(work_id)
    selected_ids = list(dict.fromkeys(x.strip() for x in selected_ids))
    selected_works = []
    for wid in selected_ids:
        w = storage.get_work(wid)
        if not w:
            return jsonify({"error": f"Произведение не найдено: {wid}"}), 404
        selected_works.append(w)

    active = storage.load_blocking_cases()
    active_ids = {c.get("id") for c in active}
    all_cases = active + [c for c in storage.load_report_archive() if c.get("id") not in active_ids]
    in_period = [c for c in all_cases if reports.case_in_period(c, date_from, date_to)]

    if selected_works:
        author_ids = list(dict.fromkeys(w["author_id"] for w in selected_works))
        authors = [storage.get_author(a) for a in author_ids]
    elif author_id:
        a = storage.get_author(author_id)
        if not a:
            return jsonify({"error": "Автор не найден"}), 404
        authors = [a]
    else:
        authors = storage.load_authors()

    groups = []
    for author in [a for a in authors if a]:
        works = storage.list_works_by_author(author["id"])
        if selected_works:
            works = [w for w in works if w["id"] in selected_ids]
        author_cases = [c for c in in_period
                        if _norm_title(c.get("author_name")) == _norm_title(author["name"])
                        or any(c.get("work_id") == w["id"] for w in storage.list_works_by_author(author["id"]))]
        used = set()
        works_with_cases = []
        for w in works:
            wc = [c for c in author_cases
                  if c.get("work_id") == w["id"] or _norm_title(c.get("work_title")) == _norm_title(w["title"])]
            used.update(c["id"] for c in wc)
            works_with_cases.append((w, wc))
        other = [] if selected_works else [c for c in author_cases if c["id"] not in used]
        if not any(cs for _w, cs in works_with_cases) and not other and not (author_id or selected_works):
            continue  # у автора нет событий в периоде — в общий отчёт не включаем
        personal = author_personal_data.get(author["id"]) or {}
        author_for_report = dict(author)
        for field in ("customer_name", "customer_director", "contract_number", "contract_date", "monthly_fee"):
            author_for_report[field] = personal.get(field, "")
        fee_override = (request.args.get("fee") or "").strip()
        if fee_override and len(authors) == 1:
            author_for_report["monthly_fee"] = fee_override  # сумма за период, исправленная в окне отчёта
        works_with_cases = [(w, cs) for w, cs in works_with_cases if cs or selected_works or author_id]
        groups.append({"author": author_for_report, "works": works_with_cases, "other_cases": other,
                       "act_works": [w for w, _ in works_with_cases]})

    xlsx = reports.build_protection_report(groups, date_from, date_to, storage.get_firm_letterhead())
    from urllib.parse import quote as _q
    if selected_works:
        if len(authors) == 1:
            scope = authors[0]["name"].split(" ")[0] + "_" + (
                selected_works[0]["title"] if len(selected_works) == 1 else f"{len(selected_works)}_произведения")
        else:
            scope = f"{len(selected_works)}_произведений_{len(authors)}_авторов"
    elif author_id:
        scope = authors[0]["name"].split(" ")[0]
    else:
        scope = "все_авторы"
    scope = re.sub(r"[\\/:*?\"<>|«»]+", "", scope).replace(" ", "_")[:60]
    filename = f"Отчет_{scope}_{date_from}_{date_to}.xlsx"
    _log("сформировал отчёт для заказчика", f"{date_from} — {date_to}, {scope}")
    return Response(xlsx, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition":
                             f"attachment; filename=otchet_{date_from}_{date_to}.xlsx; filename*=UTF-8''{_q(filename)}"})


@app.get("/api/authors/<author_id>/monthly-work-report.xlsx")
@require_role("admin")
def download_author_monthly_work_report(author_id):
    """Отчёт по одному автору — по образцу реального ежемесячного отчёта
    юрфирмы: лист на каждое произведение + отдельный лист «Акт выполненных
    работ». По умолчанию — текущий календарный месяц, можно указать
    ?month=YYYY-MM для любого другого.

    Только admin — в акте печатаются коммерческие условия (номер
    договора, плата в месяц), эти данные хранятся в защищённой записи
    author_personal_data, не на самом объекте автора."""
    author = storage.get_author(author_id)
    if not author:
        return jsonify({"error": "Автор не найден"}), 404

    month_param = request.args.get("month") or time.strftime("%Y-%m")
    try:
        year_s, month_s = month_param.split("-")
        year, month = int(year_s), int(month_s)
        if not (1 <= month <= 12):
            raise ValueError
    except ValueError:
        return jsonify({"error": "Неверный формат месяца, ожидается YYYY-MM"}), 400

    period_start = f"{year:04d}-{month:02d}-01"
    last_day = monthrange(year, month)[1]
    period_end = f"{year:04d}-{month:02d}-{last_day:02d}"

    works = storage.list_works_by_author(author_id)
    all_cases = storage.load_blocking_cases()
    works_with_cases = []
    for w in works:
        # Сопоставляем по автору+названию (текстом), не только по work_id —
        # при добавлении через «Поиск по сайтам» work_id иногда остаётся
        # пустым (там поиск не привязан к конкретному произведению), а
        # автор+название заполняются всегда.
        cases_for_work = [
            c for c in all_cases
            if c.get("work_id") == w["id"]
            or ((c.get("author_name") or "") == author["name"] and (c.get("work_title") or "") == w["title"])
        ]
        works_with_cases.append((w, cases_for_work))

    # Реквизиты заказчика/договора теперь хранятся в защищённой записи, не
    # на самом объекте автора — собираем их сюда перед передачей в
    # reports.build_author_monthly_workbook (которая ждёт их как обычные
    # поля словаря "author", как и раньше, ей саму смену места хранения
    # знать не нужно).
    personal_fields = author_personal_data.get(author_id) or {}
    author_for_report = dict(author)
    for field in ("customer_name", "customer_director", "contract_number", "contract_date", "monthly_fee"):
        author_for_report[field] = personal_fields.get(field, "")

    firm_letterhead = storage.get_firm_letterhead()
    xlsx_bytes = reports.build_author_monthly_workbook(author_for_report, works_with_cases, period_start, period_end, firm_letterhead)

    safe_author = re.sub(r"[^A-Za-z0-9_-]", "_", author["name"]) or "author"
    filename = f"otchet_{safe_author}_{year:04d}-{month:02d}.xlsx"
    return Response(
        xlsx_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/api/blocking-cases/monthly-report/finalize")
@require_role("editor")
def finalize_monthly_blocking_report():
    """Отдельное явное действие (не GET, чтобы случайно не сработало от
    предзагрузки ссылки): скачивает тот же отчёт, но ПОСЛЕ этого убирает
    вошедшие в него дела из активной таблицы «Блокировка» и переносит их
    в архив отчётов по каждому автору — чтобы список активных дел не
    захламлялся завершёнными, но история никуда не терялась."""
    data = request.get_json(force=True) or {}
    month_param = data.get("month")
    if not month_param or "-" not in month_param:
        return jsonify({"error": "Укажите месяц в формате YYYY-MM"}), 400
    try:
        year_s, month_s = month_param.split("-")
        year, month = int(year_s), int(month_s)
        if not (1 <= month <= 12):
            raise ValueError
    except ValueError:
        return jsonify({"error": "Неверный формат месяца, ожидается YYYY-MM"}), 400

    cases = storage.load_blocking_cases()
    xlsx_bytes = reports.build_monthly_report(cases, year, month)
    report_cases = reports.cases_for_month(cases, year, month)
    # в архив уходят только по-настоящему закрытые дела (is_blocked И не
    # needs_resend — то есть заблокировано и на текущий момент проверка
    # подтверждает, что ссылка по-прежнему недоступна) — если проверка
    # нашла, что ссылка снова ожила (needs_resend), дело остаётся в
    # активной таблице, ему ещё нужно повторное обращение
    archived_cases = [c for c in report_cases if link_check.is_blocked(c) and not c.get("needs_resend")]
    storage.archive_reported_cases(archived_cases, year, month)
    _log(
        "завершил и заархивировал отчёт за месяц",
        f"{year:04d}-{month:02d}: {len(archived_cases)} дел(о) убрано из активной таблицы",
    )

    filename = f"otchet_blokirovka_{year:04d}-{month:02d}.xlsx"
    return Response(
        xlsx_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/authors/<author_id>/report-archive")
def get_author_report_archive(author_id):
    author = storage.get_author(author_id)
    if not author:
        return jsonify({"error": "Автор не найден"}), 404
    return jsonify([_case_for_client(e) for e in storage.get_report_archive_for_author(author["name"])])


@app.get("/api/report-archive")
def list_all_report_archive():
    """Весь архив отчётов сразу, для обзорного раздела «Архив» в левом
    меню (см. заметку разработки, 02.09) — раньше архив был виден только
    по одному автору за раз, через маленькую иконку 📁 в дереве. С
    появлением автоматической мгновенной архивации (см.
    _maybe_auto_archive_blocked_case) архив стал использоваться регулярно,
    не раз в месяц — понадобился полноценный обзорный раздел."""
    return jsonify([_case_for_client(e) for e in storage.load_report_archive()])


@app.post("/api/report-archive/<case_id>/restore")
@require_role("editor")
def restore_archived_blocking_case(case_id):
    """На случай ошибки при «Завершить месяц и заархивировать» — возвращает
    дело обратно в активную таблицу «Блокировка»."""
    restored = storage.restore_archived_case(case_id)
    if not restored:
        return jsonify({"error": "В архиве нет дела с таким ID"}), 404
    _log("восстановил дело из архива отчётов", f"{restored.get('title')} ({restored.get('url')})")
    return jsonify(restored)


@app.post("/api/blocking-cases/<case_id>/check-link")
@require_role("editor")
def check_link_now(case_id):
    """Ручная проверка доступности ссылки — не ждать 14 дней или часовой
    цикл фонового наблюдателя. Работает в любой момент (не только после
    подачи заявления), это просто обычная проверка «отвечает ли сайт»."""
    updated = jobs.check_case_now(case_id)
    if not updated:
        return jsonify({"error": "Дело не найдено"}), 404
    _log("проверил доступность ссылки", f"{updated['url']}: {updated['link_status']}")
    return jsonify(_case_for_client(updated))


@app.get("/api/audit-log")
@require_role("admin")
def get_audit_log():
    limit = min(int(request.args.get("limit", 200)), 2000)
    return jsonify(storage.load_audit_log(limit))


@app.get("/api/complaint-send-log")
@require_role("admin")
def get_complaint_send_log():
    """Отдельный от общего журнала действий — специально под «кто когда
    что отправил» (претензии, жалобы Avito/Google DMCA, заявления/РКН) по
    конкретным делам. Только admin."""
    limit = min(int(request.args.get("limit", 500)), 5000)
    entries = storage.load_complaint_send_log(limit)
    for e in entries:
        e["type_label"] = storage.COMPLAINT_SEND_TYPES.get(e.get("type", ""), e.get("type", ""))
    return jsonify(entries)


# ---------- аналитика (только admin) ----------
@app.get("/api/analytics/summary")
@require_role("admin")
def get_analytics_summary():
    """Три помесячных среза разом — сколько обнаружено, сколько
    заблокировано, и сравнение динамики между ними. Только admin — та же
    логика, что и у журнала действий: это управленческая сводка, не
    рабочий инструмент для повседневной работы редактора.

    Поверх автоматического подсчёта накладываются ручные поправки (см.
    /api/analytics/overrides) — если админ поправил какое-то число, здесь
    оно уже подставлено, а не исходное. Флаг "overridden" в ответе на
    каждый месяц показывает фронтенду, какие цифры поправлены вручную."""
    months = min(max(int(request.args.get("months", 12)), 1), 36)
    audit_log = storage.load_audit_log(storage.AUDIT_LOG_MAX_ENTRIES)
    cases = storage.load_blocking_cases()
    archived = storage.load_report_archive()
    overrides = storage.load_analytics_overrides()

    detected = analytics.detected_per_month(audit_log, months=months)
    blocked = analytics.blocked_per_month(cases, archived, months=months)
    dynamics = analytics.spread_dynamics(audit_log, cases, archived, months=months)

    detected["counts"], detected["overridden"] = analytics.apply_overrides(
        detected["months"], detected["counts"], overrides["detected"])
    blocked["counts"], blocked["overridden"] = analytics.apply_overrides(
        blocked["months"], blocked["counts"], overrides["blocked"])
    # график динамики использует те же (уже поправленные) числа — иначе
    # поправка отражалась бы в первых двух разделах, но не в третьем
    dynamics["detected_counts"], _ = analytics.apply_overrides(
        dynamics["months"], dynamics["detected_counts"], overrides["detected"])
    dynamics["blocked_counts"], _ = analytics.apply_overrides(
        dynamics["months"], dynamics["blocked_counts"], overrides["blocked"])

    return jsonify({"detected": detected, "blocked": blocked, "dynamics": dynamics})


@app.put("/api/analytics/overrides")
@require_role("admin")
def set_analytics_override_endpoint():
    """Вручную поправить (или сбросить) число за конкретный месяц —
    на случай, если автоматический подсчёт что-то не учёл. value=null
    сбрасывает поправку обратно к автоматическому значению."""
    data = request.get_json(force=True) or {}
    metric = data.get("metric")
    month = data.get("month")
    value = data.get("value")

    if metric not in ("detected", "blocked"):
        return jsonify({"error": "metric должен быть 'detected' или 'blocked'"}), 400
    if not month or not re.match(r"^\d{4}-\d{2}$", str(month)):
        return jsonify({"error": "month должен быть в формате YYYY-MM"}), 400
    if value is not None:
        try:
            value = int(value)
        except (TypeError, ValueError):
            return jsonify({"error": "value должен быть целым числом или null (чтобы сбросить поправку)"}), 400
        if value < 0:
            return jsonify({"error": "value не может быть отрицательным"}), 400

    storage.set_analytics_override(metric, month, value)
    _log(
        "изменил цифру в аналитике",
        f"{metric} {month}: {'сброшено к автоматическому' if value is None else value}",
    )
    return jsonify({"ok": True})


@app.get("/api/analytics/export.xlsx")
@require_role("admin")
def export_analytics_xlsx():
    """Скачивание аналитики в Excel — с уже применёнными ручными
    поправками (то же самое, что видно на экране, не сырые автоматические
    цифры)."""
    months = min(max(int(request.args.get("months", 12)), 1), 36)
    audit_log = storage.load_audit_log(storage.AUDIT_LOG_MAX_ENTRIES)
    cases = storage.load_blocking_cases()
    archived = storage.load_report_archive()
    overrides = storage.load_analytics_overrides()

    detected = analytics.detected_per_month(audit_log, months=months)
    blocked = analytics.blocked_per_month(cases, archived, months=months)
    dynamics = analytics.spread_dynamics(audit_log, cases, archived, months=months)
    detected["counts"], detected["overridden"] = analytics.apply_overrides(
        detected["months"], detected["counts"], overrides["detected"])
    blocked["counts"], blocked["overridden"] = analytics.apply_overrides(
        blocked["months"], blocked["counts"], overrides["blocked"])
    dynamics["detected_counts"], _ = analytics.apply_overrides(
        dynamics["months"], dynamics["detected_counts"], overrides["detected"])
    dynamics["blocked_counts"], _ = analytics.apply_overrides(
        dynamics["months"], dynamics["blocked_counts"], overrides["blocked"])

    xlsx_bytes = reports.build_analytics_report(detected, blocked, dynamics)
    _log("скачал отчёт по аналитике", f"{months} мес.")
    return Response(
        xlsx_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=analitika_{months}mes.xlsx"},
    )




# Фоновый наблюдатель за доступностью ссылок после подачи заявления — см.
# jobs.py. Запускается один раз при импорте модуля (и через gunicorn, и
# через python -m backend.app — оба пути импортируют этот файл), не
# только в блоке if __name__ == "__main__" ниже, который под gunicorn не
# выполняется вовсе.
jobs.start_link_watcher()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
