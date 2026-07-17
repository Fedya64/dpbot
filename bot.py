import os
import logging
import sqlite3
from datetime import datetime
from bs4 import BeautifulSoup
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
    conn = sqlite3.connect("slots.db")
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
    conn.close()

# === Playwright глобальные объекты ===
playwright = None
browser = None
context = None

async def init_browser():
    global playwright, browser, context
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
    context = await browser.new_context()

async def close_browser():
    global playwright, browser, context
    if context:
        await context.close()
    if browser:
        await browser.close()
    if playwright:
        await playwright.stop()

async def fetch_page(url: str) -> tuple[str, int]:
    global context
    page = await context.new_page()
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
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
        if "cloudflare" in low_html:
            logging.warning("Cloudflare обнаружена")
        if "attention required" in low_html:
            logging.warning("Страница Cloudflare")
        if "forbidden" in low_html:
            logging.warning("Forbidden")

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
            soup = BeautifulSoup(html, "html.parser")
            page_text = soup.get_text(separator=" ").strip()
            slots_available = "Наразі всі місця зайняті" not in page_text

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
            conn = sqlite3.connect("slots.db")
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO slots (city, chat_id, opened_at, weekday, hour)
                VALUES (?, ?, ?, ?, ?)
                """,
                (city, chat_id, now.isoformat(), now.weekday(), now.hour),
            )
            conn.commit()
            conn.close()

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
            conn = sqlite3.connect("slots.db")
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
            conn.close()

    except Exception as e:
        logging.error(f"Помилка перевірки слотів для {chat_id}/{city}: {e}")

# === MAIN ===
async def main():
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        raise RuntimeError("Не задано TOKEN в змінних оточення.")

    init_db()
    await init_browser()

    application = ApplicationBuilder().token(TOKEN).build()

    async def _startup(app):
        await app.bot.delete_webhook(drop_pending_updates=True)
        logging.info("Scheduler started")
        logging.info("Application started")

    application.post_init = _startup

    try:
        await application.run_polling()
    finally:
        await close_browser()

if __name__ == "__main__":
    asyncio.run(main())
