"""Экспорт результатов: CSV (всегда доступен) и Telegram-уведомление (опционально,
если задан TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID).

Экспорт в Google Sheets в этой сборке не включён (у оригинального сценария он был
завязан на конкретные приватные таблицы конкретных клиентов — их нет смысла
переносить как «универсальную» фичу). Если понадобится — это делается через
пакет gspread и сервисный аккаунт Google Cloud, см. README.
"""
import csv
import io
import os
import time

import requests

from . import appeals as appeals_mod


def results_to_csv(results):
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM, чтобы Excel корректно определял UTF-8 с кириллицей
    writer = csv.DictWriter(buf, fieldnames=["position", "source", "title", "url", "description"])
    writer.writeheader()
    for r in results:
        writer.writerow({
            "position": r.get("position", ""),
            "source": r.get("source", ""),
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "description": r.get("description", ""),
        })
    return buf.getvalue()


def blocking_cases_to_csv(cases):
    buf = io.StringIO()
    buf.write("\ufeff")
    fields = [
        "author_name", "work_title", "source", "title", "url",
        "presence_google", "presence_yandex",
        "defendant", "defendant_email", "ip_address",
        "claim_date", "claim_decision", "appeals_text",
        "block_date", "notes", "petition_filed_at",
        "link_status", "link_checked_at",
    ]
    headers = {
        "author_name": "Автор", "work_title": "Произведение", "source": "Источник",
        "title": "Заголовок", "url": "Ссылка",
        "presence_google": "В выдаче Google", "presence_yandex": "В выдаче Яндекс",
        "defendant": "Ответчик", "defendant_email": "Email ответчика", "ip_address": "IP-адрес",
        "claim_date": "Дата претензии", "claim_decision": "Решение по претензии",
        "appeals_text": "Обращения: МГС (дата определения, №) / РКН (дата, №) / статус",
        "block_date": "Дата блокировки",
        "notes": "Примечания",
        "petition_filed_at": "Дата подачи заявления",
        "link_status": "Доступность ссылки", "link_checked_at": "Дата проверки ссылки",
    }
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writerow(headers)
    for c in cases:
        row = {k: c.get(k, "") for k in fields}
        row["appeals_text"] = "\n".join(appeals_mod.summary_lines(c))
        for bf in ("presence_google", "presence_yandex"):
            row[bf] = "да" if row[bf] else ""
        if row.get("link_checked_at"):
            row["link_checked_at"] = time.strftime("%d.%m.%Y", time.localtime(row["link_checked_at"]))
        writer.writerow(row)
    return buf.getvalue()


def telegram_is_configured():
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN")) and bool(os.environ.get("TELEGRAM_CHAT_ID"))


def send_telegram_summary(work_title, pipeline, author_name=""):
    if not telegram_is_configured():
        raise RuntimeError("Telegram не настроен: заполните TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID в .env")

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    n = pipeline["after_dedupe"]
    title = f"{author_name} — {work_title}" if author_name else work_title
    text = (
        f"🔎 Мониторинг «{title}»\n"
        f"Найдено ссылок: {pipeline['raw_count']}\n"
        f"После исключения официальных доменов: {pipeline['after_domain_exclude']}\n"
        f"После фильтра по ключевым словам: {pipeline['after_keyword_filter']}\n"
        f"После удаления дублей: {n}\n"
    )
    if n:
        text += "\nПервые ссылки:\n" + "\n".join(f"• {r['url']}" for r in pipeline["results"][:5])

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()
