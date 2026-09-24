"""Простой менеджер фоновых задач в памяти процесса (threading).
Для одного пользователя/небольшой команды этого достаточно — не требует Redis/Celery.
"""
import threading
import time
import traceback
import uuid

from . import search_sources
from . import site_search
from . import filters
from . import storage
from . import screenshot_capture

_jobs = {}
_jobs_lock = threading.Lock()

_site_jobs = {}
_site_jobs_lock = threading.Lock()

_STAGGER_CHUNK_SEC = 0.5  # дробим ожидание в очереди на такие кусочки —
# чтобы отмена ещё не начавшейся (queued) задачи срабатывала быстро, а не
# только после того, как истечёт вся её отложенная задержка старта


def _with_ids(items):
    out = []
    for it in items:
        it = dict(it)
        it["id"] = str(uuid.uuid4())[:8]
        out.append(it)
    return out


def _mark_already_blocked(items, work_id=None):
    """Проставляет already_in_blocking у результатов поиска, чьи ссылки уже
    есть в активной таблице «Блокировка» — иначе повторный поиск (или
    объединение результатов поиска по произведению и поиска по сайтам)
    каждый раз показывает уже разобранные ссылки как будто новые, и
    приходится заново решать по одному и тому же адресу.

    С уникальностью «в рамках произведения» (не глобальной — см.
    storage.add_blocking_case, 03.09) этот бейдж тоже должен смотреть
    только на дела ТОГО ЖЕ произведения, если work_id известен — иначе
    ссылка выглядела бы «уже добавлено» из-за дела совсем другого автора,
    хотя реально её ещё можно добавить под этим произведением. Для
    контекста «Поиск по сайтам» (work_id всегда None — результаты не
    привязаны к конкретному произведению до «Прикрепить») сознательно
    остаётся старая, глобальная проверка — там заранее не известно, под
    какое произведение ссылку в итоге отправят."""
    all_cases = storage.load_blocking_cases()
    if work_id:
        already = {storage._normalize_url_for_dedup(c["url"]) for c in all_cases if c.get("work_id") == work_id}
    else:
        already = {storage._normalize_url_for_dedup(c["url"]) for c in all_cases}
    for it in items:
        it["already_in_blocking"] = storage._normalize_url_for_dedup(it.get("url")) in already
    return items


def _sleep_interruptible(seconds, is_cancelled):
    """time.sleep, но кусками — чтобы отмена сработала быстро, не дожидаясь
    полной задержки целиком."""
    end = time.time() + seconds
    while time.time() < end:
        if is_cancelled():
            return
        time.sleep(min(_STAGGER_CHUNK_SEC, max(0, end - time.time())))


def _run_job(job_id, work, author_name, start_delay=0, on_finish=None):
    job = _jobs[job_id]

    def is_cancelled():
        return job.get("cancel_requested", False)

    if start_delay > 0:
        # остаётся "queued" на время задержки — это специально для массового
        # запуска (кнопка «Искать по всем активным»): без этого много
        # произведений одновременно бьют в один и тот же внешний API и
        # получают 429 (слишком много запросов)
        _sleep_interruptible(start_delay, is_cancelled)

    if is_cancelled():
        job["status"] = "cancelled"
        job["finished_at"] = time.time()
        if on_finish:
            on_finish(work["id"], "cancelled")
        return

    try:
        job["status"] = "running"

        def progress_cb(task_idx, total_tasks, page, total_pages, source_label):
            job["progress"] = {
                "task": task_idx + 1,
                "total_tasks": total_tasks,
                "page": page,
                "total_pages": total_pages,
                "source": source_label,
            }

        blocked = storage.load_blocklist() + work.get("extra_blocked_domains", [])
        sources = work.get("sources") or {"yandex": True}
        source_report = {}
        raw_items, demo_mode = search_sources.run_search(
            work["query"], work.get("pages", 7), sources, progress_cb, should_stop=is_cancelled,
            report=source_report,
        )
        job["demo_mode"] = demo_mode
        job["source_report"] = source_report

        pipeline = filters.run_pipeline(
            raw_items,
            work.get("keywords", []),
            blocked,
            work.get("negative_keywords", []),
        )
        pipeline["results"] = _mark_already_blocked(_with_ids(pipeline["results"]), work_id=work["id"])
        pipeline["all_results"] = _mark_already_blocked(_with_ids(pipeline["all_results"]), work_id=work["id"])
        pipeline["source_report"] = source_report
        job["result"] = pipeline
        job["finished_at"] = time.time()

        # Сохраняем «постоянный» редактируемый список результатов по произведению —
        # в т.ч. если поиск был остановлен вручную на середине: то, что успели
        # найти до остановки, всё равно стоит сохранить, а не выбрасывать.
        # Если фильтр по словам что-то нашёл — сохраняем его, иначе сохраняем
        # весь список найденного (после исключения официалов), чтобы было что
        # смотреть и редактировать руками, даже если ни одно ключевое слово не совпало.
        # is_fallback=True явно помечает второй случай, чтобы в интерфейсе не
        # выглядело так, будто это отфильтрованный результат.
        is_fallback = not pipeline["results"]
        to_persist = pipeline["all_results"] if is_fallback else pipeline["results"]
        storage.save_work_results(work["id"], to_persist, is_fallback=is_fallback)

        job["status"] = "cancelled" if is_cancelled() else "done"
        if on_finish:
            on_finish(work["id"], job["status"])
    except Exception as e:  # noqa
        job["status"] = "error"
        job["error"] = str(e)
        job["traceback"] = traceback.format_exc()
        job["finished_at"] = time.time()
        if on_finish:
            on_finish(work["id"], "error")


def start_job(work, author_name="", start_delay=0, on_finish=None):
    job_id = str(uuid.uuid4())[:12]
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "work_id": work["id"],
            "work_title": work["title"],
            "author_name": author_name,
            "status": "queued",
            "progress": {"task": 0, "total_tasks": 1, "page": 0, "total_pages": work.get("pages", 7), "source": ""},
            "started_at": time.time(),
            "result": None,
            "error": None,
            "demo_mode": None,
            "cancel_requested": False,
        }
    t = threading.Thread(target=_run_job, args=(job_id, work, author_name, start_delay, on_finish), daemon=True)
    t.start()
    return job_id


def cancel_job(job_id):
    job = _jobs.get(job_id)
    if not job:
        return None
    if job["status"] in ("queued", "running"):
        job["cancel_requested"] = True
    return job


def cancel_all_jobs():
    """Отменяет все ещё не завершённые задачи поиска по произведениям —
    для кнопки «Остановить всё» рядом с массовым запуском."""
    cancelled = []
    for job in _jobs.values():
        if job["status"] in ("queued", "running"):
            job["cancel_requested"] = True
            cancelled.append(job["id"])
    return cancelled


def get_job(job_id):
    return _jobs.get(job_id)


def list_jobs():
    return sorted(_jobs.values(), key=lambda j: j["started_at"], reverse=True)


# ---------- фоновая задача для «Поиск по сайтам» ----------
# Выделено отдельно от обычных задач поиска по произведению — другая форма
# результата (плоский список найденного по сайтам + список ошибок по
# сайтам) и другой смысл прогресса (номер сайта, а не номер страницы выдачи).
# Понадобилось, когда справочник сайтов вырос до полутора сотен доменов —
# без фоновой задачи один HTTP-запрос синхронно ждал бы прохода по всем
# сайтам целиком (до нескольких десятков минут при таймауте 20с на сайт),
# без какого-либо прогресса на экране всё это время.
def _save_site_statuses(site_report):
    """Запоминает у каждого сайта итог последней проверки — для фильтра
    «Требуют настройки» и статистики в справочнике."""
    now = time.time()
    for site_id, r in site_report.items():
        if not r.get("status"):
            continue
        patch = {"last_status": r["status"], "last_status_detail": r.get("detail", ""), "last_checked_at": now}
        try:
            site = storage.get_site(site_id)
            if not site:
                continue
            if r.get("found"):
                patch["last_found_at"] = now
                patch["found_total"] = int(site.get("found_total") or 0) + int(r["found"])
            storage.update_site_fields(site_id, patch)
        except Exception:  # noqa — статистика не должна ронять поиск
            pass


def _run_site_search_job(job_id, sites, queries, negative_keywords=None):
    job = _site_jobs[job_id]

    def is_cancelled():
        return job.get("cancel_requested", False)

    try:
        job["status"] = "running"

        def progress_cb(idx, total, label):
            job["progress"] = {"done": idx, "total": total, "current_site": label}

        # высокий приоритет — первыми (порядок остальных не меняется)
        prio_rank = {"high": 0, "normal": 1, "low": 2}
        sites = sorted(sites, key=lambda st: prio_rank.get(st.get("priority") or "normal", 1))
        site_report = {}
        results, errors, redirects = site_search.search_sites(
            sites, queries, progress_cb, should_stop=is_cancelled, report=site_report)
        _save_site_statuses(site_report)

        # search_sites уже дедуплицирует результаты по ссылке сама (см. её
        # докстринг) — раньше здесь ошибочно казалось, что этого шага нет.
        # Реально отсутствовавшая часть — фильтр по стоп-словам (у «Поиска
        # по произведению» он есть через work.negative_keywords, здесь не
        # было вообще никакого способа отсечь однофамильные ложные
        # срабатывания) и сверка с уже добавленными в блокировку ссылками.
        if negative_keywords:
            results = filters.filter_by_keywords(results, keywords=None, negative_keywords=negative_keywords)
        results = _mark_already_blocked(results)

        counts = {}
        for r in site_report.values():
            counts[r["status"] or "not_reached"] = counts.get(r["status"] or "not_reached", 0) + 1
        job["result"] = {
            "queries": queries, "results": results, "errors": errors,
            "redirects": redirects, "sites_searched": len(sites),
            # честные итоги: сколько сайтов реально опрошено и с каким результатом
            "site_report": [dict(v, site_id=k) for k, v in site_report.items()],
            "site_status_counts": counts,
        }
        job["status"] = "cancelled" if is_cancelled() else "done"
        job["finished_at"] = time.time()
        # Раньше результат жил только здесь, в памяти процесса (_site_jobs) —
        # при перезапуске сервера (или просто при закрытии приложения,
        # если это было отдельное окно консоли) весь список найденных
        # ссылок пропадал бесследно, даже если человек его ещё не разобрал.
        # Сохраняем последний результат на диск — при следующем открытии
        # раздела «Поиск по сайтам» (см. GET /api/sites/last-search-results
        # в app.py) он подхватится автоматически, даже после перезапуска.
        try:
            storage.save_last_site_search_result(job["result"])
        except Exception:  # noqa — сама задача уже успешно завершена, не должна падать из-за диска
            pass
    except Exception as e:  # noqa
        job["status"] = "error"
        job["error"] = str(e)
        job["traceback"] = traceback.format_exc()
        job["finished_at"] = time.time()


def start_site_search_job(sites, queries, negative_keywords=None):
    if isinstance(queries, str):
        queries = [queries]
    job_id = str(uuid.uuid4())[:12]
    with _site_jobs_lock:
        _site_jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "progress": {"done": 0, "total": len(sites) * max(len(queries), 1), "current_site": ""},
            "started_at": time.time(),
            "result": None,
            "error": None,
            "cancel_requested": False,
        }
    t = threading.Thread(target=_run_site_search_job, args=(job_id, sites, queries, negative_keywords), daemon=True)
    t.start()
    return job_id


def cancel_site_search_job(job_id):
    job = _site_jobs.get(job_id)
    if not job:
        return None
    if job["status"] in ("queued", "running"):
        job["cancel_requested"] = True
    return job


def get_site_search_job(job_id):
    return _site_jobs.get(job_id)


# ---------- фоновая задача для подготовки заявления в суд ----------
# Раньше сборка заявления (расшифровка документов автора и сотрудника,
# чтение всех скриншотов дел с диска, упаковка в zip) делалась синхронно
# прямо внутри одного HTTP-запроса — на сервере с одним gunicorn-воркером
# это на всё время сборки блокировало ответ для вообще всех остальных
# пользователей, а при большом числе дел/скриншотов сборка могла не
# уложиться в таймаут nginx/браузера — тогда скачивание срывалось без
# внятной причины. Тот же принцип, что уже применён к автоскриншотам
# (см. _run_screenshot_job выше) — выносим в фоновый поток, отдаём
# job_id сразу, фронтенд опрашивает готовность отдельными короткими
# запросами и скачивает результат отдельным запросом, когда готово.
_petition_jobs = {}
_petition_jobs_lock = threading.Lock()


def _run_petition_job(job_id, build_fn):
    job = _petition_jobs[job_id]
    try:
        job["status"] = "running"
        zip_bytes, filename_ascii, filename_utf8 = build_fn()
        job["result"] = {
            "zip_bytes": zip_bytes,
            "filename_ascii": filename_ascii,
            "filename_utf8": filename_utf8,
        }
        job["status"] = "done"
        job["finished_at"] = time.time()
    except Exception as e:  # noqa
        job["status"] = "error"
        job["error"] = str(e)
        job["traceback"] = traceback.format_exc()
        job["finished_at"] = time.time()


def start_petition_job(build_fn):
    """build_fn — функция без аргументов, возвращающая кортеж
    (zip_bytes, filename_ascii, filename_utf8). Вызывается в фоновом
    потоке, никак не блокирует ответ на POST-запрос, которым была
    запущена."""
    job_id = str(uuid.uuid4())[:12]
    with _petition_jobs_lock:
        _petition_jobs[job_id] = {"id": job_id, "status": "queued", "created_at": time.time()}
    t = threading.Thread(target=_run_petition_job, args=(job_id, build_fn), daemon=True)
    t.start()
    return job_id


def get_petition_job(job_id):
    return _petition_jobs.get(job_id)


# ---------- фоновая задача для автоматического скриншота ----------
# Playwright занимает до ~20 секунд на страницу — выполнять это синхронно
# внутри HTTP-запроса плохо сочетается с рекомендованным запуском сервера
# (gunicorn -w 1, один рабочий процесс — см. заметки к развёртыванию):
# пока один человек делает скриншот, все остальные пользователи иначе ждали
# бы отклика сервера на что угодно. Вынесено в фоновый поток по тому же
# принципу, что и поиск.
_shot_jobs = {}
_shot_jobs_lock = threading.Lock()

# До этого момента ограничения не было вообще: сколько кликов по кнопке
# скриншота пришло — столько процессов Chromium запускалось одновременно.
# На практике 28.08.2026 это уронило весь сервер: за минуту стартовало 9
# параллельных задач (обычный снимок + whois-подтверждение по разным
# делам), памяти не хватило, единственный gunicorn-воркер (-w 1, см.
# заметки к развёртыванию) упал и перезапустился systemd'ом — на эти
# секунды приложение было недоступно вообще всем, включая никак не
# связанные со скриншотами запросы (см. nginx error.log за этот день:
# "connect() failed (111: Connection refused)" — верный признак, что
# процесс именно упал, а не просто медленно отвечал).
#
# Семафор ниже ограничивает РЕАЛЬНОЕ количество одновременно открытых
# браузеров Chromium — не количество задач в очереди (они по-прежнему
# создаются сразу и видны в статусе как "running"/"queued" фронтенду),
# а именно фактический запуск capture_fn(). Лишние задачи просто ждут
# своей очереди внутри этой же фоновой функции, вместо того чтобы
# стартовать браузер сразу все разом.
#
# Значение 1 — самое безопасное для скромной конфигурации VPS одного
# gunicorn-воркера. Если сервер апгрейднут по памяти — можно поднять до
# 2, но не выше без отдельной проверки, сколько памяти реально свободно.
_CHROMIUM_CONCURRENCY = 1
_chromium_semaphore = threading.Semaphore(_CHROMIUM_CONCURRENCY)


def _run_screenshot_job(job_id, capture_fn):
    job = _shot_jobs[job_id]
    try:
        job["status"] = "running"
        with _chromium_semaphore:
            # Пока задача ждёт своей очереди на сам запуск браузера (если
            # семафор уже занят другой задачей) — статус остаётся
            # "running", фронтенд продолжает штатно опрашивать и просто
            # видит более долгое ожидание, без ошибок.
            result = capture_fn()
        job["result"] = result
        job["status"] = "done"
        job["finished_at"] = time.time()
    except screenshot_capture.ScreenshotCaptureError as e:
        job["status"] = "error"
        job["error"] = str(e)
        job["finished_at"] = time.time()
    except Exception as e:  # noqa
        job["status"] = "error"
        job["error"] = str(e)
        job["traceback"] = traceback.format_exc()
        job["finished_at"] = time.time()


def start_screenshot_job(url):
    """Обычный снимок страницы по прямой ссылке."""
    return _start_screenshot_job_with(lambda: screenshot_capture.capture(url))


def start_screenshot_job_with_form(url, query_value, input_selectors, submit_selectors):
    """Снимок страницы, где результат появляется только после заполнения
    формы (см. screenshot_capture.capture_with_form_query) — используется
    для русскоязычных whois-сервисов вроде 2ip.io, у которых нет прямой
    ссылки с готовым результатом по параметру в URL."""
    return _start_screenshot_job_with(lambda: screenshot_capture.capture_with_form_query(
        url, query_value, input_selectors, submit_selectors,
    ))


def start_screenshot_job_custom(capture_fn):
    """Произвольная функция снимка — например, вызывающий код может внутри
    неё самостоятельно реализовать «попробовать основной источник, при
    ошибке — запасной» (так и сделано для подтверждения хостинга в app.py:
    2ip.io в первую очередь, rdap.org как резерв)."""
    return _start_screenshot_job_with(capture_fn)


def _start_screenshot_job_with(capture_fn):
    job_id = str(uuid.uuid4())[:12]
    with _shot_jobs_lock:
        _shot_jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "started_at": time.time(),
            "result": None,
            "error": None,
        }
    t = threading.Thread(target=_run_screenshot_job, args=(job_id, capture_fn), daemon=True)
    t.start()
    return job_id


def get_screenshot_job(job_id):
    return _shot_jobs.get(job_id)


# ---------- фоновый наблюдатель за доступностью ссылок после подачи заявления ----------
# Раз в час просматривает все дела и проверяет те, где заявление подано
# 14+ дней назад, а проверки ещё не было. Не нужен отдельный шедулер/cron —
# простой демон-поток, запускается один раз при старте приложения (см.
# link_watcher.start() в app.py), тот же принцип, что и у остальных
# фоновых задач в этом файле.
from . import link_check  # noqa: E402

LINK_WATCHER_INTERVAL_SEC = 3600
SYSTEM_ACTOR = "система (фоновая проверка)"  # log_action(None, ...) тихо ничего не пишет — реальный
# баг, найденный при самокритике: любые автоматические переходы статуса и
# отметки needs_resend раньше не попадали в журнал вообще


def _details_text(details):
    if not details:
        return ""
    parts = []
    if details.get("http_code"):
        parts.append(f"код {details['http_code']}")
    if details.get("final_url"):
        parts.append(details["final_url"])
    if details.get("title"):
        parts.append(f"«{details['title']}»")
    if details.get("stub"):
        parts.append("заглушка о блокировке")
    if details.get("error"):
        parts.append(details["error"])
    return f" ({', '.join(parts)})" if parts else ""


def _check_due_cases_once():
    for case in storage.load_blocking_cases():
        if not link_check.is_due(case):
            continue
        details = {}
        status, checked_at = link_check.check(case["url"], details)
        patch = link_check.build_update_patch(case, status, checked_at, details)
        storage.update_blocking_case(case["id"], patch)
        detail = f"{case['url']}: {patch['link_status']}{_details_text(details)}"
        if patch.get("status"):
            detail += f" — статус автоматически изменён на «{patch['status']}»"
        storage.log_action(SYSTEM_ACTOR, "автоматическая проверка доступности ссылки", detail)

    _check_due_archived_cases_once()


def _check_due_archived_cases_once():
    """Дела, заархивированные автоматически сразу после «заблокировано»
    (см. app.py, _maybe_auto_archive_blocked_case — «Вариант 2» по
    прямому выбору пользователя, 01.09: мгновенная архивация, а не
    ожидание первой проверки), больше не видны в активной «Блокировке»,
    но мониторинг доступности ссылки по ним НЕ прекращается — иначе
    ожившую после блокировки ссылку никто бы не заметил, а раньше
    (до этой доработки) мониторинг автоматически прекращался просто
    потому, что дело уходило из storage.load_blocking_cases() — это
    было осознанным поведением при РУЧНОЙ ежемесячной архивации (см.
    комментарий в link_check.is_due), но перестало подходить, когда
    архивация стала автоматической и мгновенной.

    Если проверка находит, что архивная ссылка снова доступна — дело
    автоматически возвращается в активную «Блокировку» (той же функцией,
    что и ручная кнопка «Восстановить из архива»), needs_resend
    выставляется сразу же, чтобы сотрудник сразу увидел, что нужно
    повторное обращение."""
    for entry in storage.load_report_archive():
        if not link_check.is_due(entry):
            continue
        details = {}
        status, checked_at = link_check.check(entry["url"], details)
        patch = link_check.build_update_patch(entry, status, checked_at, details)
        if not patch["needs_resend"]:
            # всё ещё недоступна (или отвечает ровно так же, как в момент,
            # когда сотрудник отметил «ложная тревога») — фиксируем время
            # проверки прямо в архивной записи, никуда её не перенося
            storage.update_report_archive_entry(entry["id"], {k: v for k, v in patch.items() if k != "needs_resend"})
            continue

        # ссылка снова ожила — возвращаем дело в активную «Блокировку»
        # вместе с подробностями ответа, чтобы сотрудник сразу видел, реальный
        # это сайт или заглушка (и мог нажать «Ложная тревога»)
        restored = storage.restore_archived_case(entry["id"])
        if restored is None:
            continue  # кто-то успел восстановить/удалить это же дело параллельно — не задваиваем
        storage.update_blocking_case(restored["id"], patch)
        storage.log_action(
            SYSTEM_ACTOR,
            "автоматически восстановил дело из архива — ссылка снова доступна",
            f"{entry.get('title', '')} ({entry['url']}){_details_text(details)}",
        )


def _link_watcher_loop():
    while True:
        try:
            _check_due_cases_once()
        except Exception:  # noqa — фоновый цикл не должен падать насовсем из-за одной ошибки сети
            pass
        time.sleep(LINK_WATCHER_INTERVAL_SEC)


_link_watcher_started = False


def start_link_watcher():
    """Безопасно вызывать несколько раз — реально запускает поток только
    один раз за жизнь процесса."""
    global _link_watcher_started
    if _link_watcher_started:
        return
    _link_watcher_started = True
    threading.Thread(target=_link_watcher_loop, daemon=True).start()


def check_case_now(case_id):
    """Ручная проверка одного дела по кнопке «Проверить сейчас» — не ждёт
    ни 14 дней, ни часового цикла."""
    case = storage.get_blocking_case(case_id)
    if not case:
        return None
    details = {}
    status, checked_at = link_check.check(case["url"], details)
    patch = link_check.build_update_patch(case, status, checked_at, details)
    return storage.update_blocking_case(case_id, patch)
