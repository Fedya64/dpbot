import os
import logging
import sqlite3
from datetime import datetime
from typing import Optional
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from playwright.async_api import async_playwright
import asyncio

# === ЛОГИ ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
)

# === ГОРОДА ===
CITIES = {
    "Мюнхен": "https://munich.pasport.org.ua/solutions/e-queue",
    "Берлін": "https://berlin.pasport.org.ua/solutions/e-queue",
    "Прага": "https://prague.pasport.org.ua/solutions/e-queue",
    "Варшава": "https://warsaw.pasport.org.ua/solutions/e-queue",
}

CITY_EMOJI = {
    "Мюнхен": "🟢",
    "Берлін": "🔵",
    "Прага": "🟣",
    "Варшава": "🟠",
}

user_city: dict[int, str] = {}
last_status: dict[tuple[int, str], bool] = {}
active_monitoring: dict[int, bool] = {}
debug_checks: list[dict] = []

CHECK_INTERVAL = 60  # одна хвилина

# === БАЗА ДЛЯ СТАТИСТИКИ ===
def init_db() -> None:
    with sqlite3.connect("slots.db") as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city TEXT,
                chat_id INTEGER,
                opened_at TEXT,
                closed_at TEXT,
                duration_min REAL,
                weekday INTEGER,
                hour INTEGER
            )
            """
        )
        conn.commit()

# === Playwright глобальные объекты ===
playwright = None
browser = None
browser_context = None

async def init_browser():
    global playwright, browser, browser_context
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
    browser_context = await browser.new_context()

async def close_browser():
    global playwright, browser, browser_context
    if browser_context:
        await browser_context.close()
    if browser:
        await browser.close()
    if playwright:
        await playwright.stop()

async def fetch_page(url: str) -> tuple[str, Optional[int]]:
    global browser_context
    page = await browser_context.new_page()
    try:
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            logging.warning(f"Ошибка загрузки {url}: {e}")
            return "", None

        status = response.status if response else None
        if status != 200:
            logging.warning(f"HTTP {status} для {url}")
            return "", status

        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            logging.info("networkidle не наступил, продолжаем")

        title = await page.title()
        logging.info(f"Title: {title}")

        html = await page.content()
        low_html = html.lower()

        if "cloudflare" in low_html or "attention required" in low_html or status in (403, 503):
            logging.warning("Cloudflare/Forbidden detected")

        return html, status
    finally:
        await page.close()

# === МЕНЮ ===
def main_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        ["🔄 Статус", "🏙 Змінити місто"],
        ["⛔ Зупинити моніторинг", "▶️ Увімкнути моніторинг"],
        ["📊 Статистика термінів"],
        ["🕓 Останній термін"],
        ["⏱ Середня тривалість"],
        ["📅 Найчастіший день"],
        ["⏰ Пікова година"],
        ["🛠 Debug"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# === ПРОВЕРКА СЛОТОВ ===
async def check_slots(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.chat_id
    if not active_monitoring.get(chat_id, False):
        return

    city = user_city.get(chat_id, "Мюнхен")
    url = CITIES[city]
    emoji = CITY_EMOJI[city]

    try:
        html, status = await fetch_page(url)

        if not html or status != 200:
            logging.warning(f"[{chat_id}] {city}: статус {status}, слоты считаем недоступными")
            slots_available = False
        else:
            slots_available = "наразі всі місця зайняті" not in html.lower()

        debug_checks.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "city": city,
            "available": slots_available,
        })
        if len(debug_checks) > 5:
            debug_checks.pop(0)

        key = (chat_id, city)

        if slots_available and not last_status.get(key, False):
            last_status[key] = True
            now = datetime.now()
            with sqlite3.connect("slots.db") as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO slots (city, chat_id, opened_at, weekday, hour)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (city, chat_id, now.isoformat(), now.weekday(), now.hour),
                )
                conn.commit()

            msg = (
                f"{emoji} {city.upper()} — З'ЯВИЛИСЬ ВІЛЬНІ ТЕРМІНИ!\n"
                f"📅 Паспортний сервіс\n"
                f"🔗 Натисніть, щоб записатися:"
            )
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Перейти до запису", url=url)]]
            )
            await context.bot.send_message(chat_id=chat_id, text=msg, reply_markup=keyboard)

        elif not slots_available and last_status.get(key, False):
            last_status[key] = False
            with sqlite3.connect("slots.db") as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT id, opened_at FROM slots
                    WHERE city = ? AND chat_id = ? AND closed_at IS NULL
                    ORDER BY id DESC LIMIT 1
                    """,
                    (city, chat_id),
                )
                row = cur.fetchone()
                if row:
                    slot_id, opened_at = row
                    opened_dt = datetime.fromisoformat(opened_at)
                    closed_dt = datetime.now()
                    duration = (closed_dt - opened_dt).total_seconds() / 60.0
                    cur.execute(
                        """
                        UPDATE slots
                        SET closed_at = ?, duration_min = ?
                        WHERE id = ?
                        """,
                        (closed_dt.isoformat(), duration, slot_id),
                    )
                    conn.commit()

    except Exception as e:
        logging.error(f"Помилка перевірки слотів для {chat_id}/{city}: {e}")

# === КОМАНДЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_city[chat_id] = "Мюнхен"
    active_monitoring[chat_id] = True

    jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    for job in jobs:
        job.schedule_removal()

    context.job_queue.run_repeating(
        check_slots,
        interval=CHECK_INTERVAL,
        first=5,
        chat_id=chat_id,
        name=str(chat_id)
    )

    await update.message.reply_text(
        "Вітаю! Моніторинг запущено.",
        reply_markup=main_menu()
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    active_monitoring[chat_id] = False

    jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    for job in jobs:
        job.schedule_removal()

    last_status.pop((chat_id, user_city.get(chat_id, "Мюнхен")), None)

    await update.message.reply_text("Моніторинг зупинено.")

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id

    if text == "🔄 Статус":
        await update.message.reply_text(
            "Моніторинг активний." if active_monitoring.get(chat_id) else "Моніторинг вимкнено."
        )
    elif text == "🏙 Змінити місто":
        await update.message.reply_text(
            "Оберіть місто:",
            reply_markup=ReplyKeyboardMarkup([list(CITIES.keys())
