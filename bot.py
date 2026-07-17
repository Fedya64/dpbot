import logging
import sqlite3
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# === НАСТРОЙКИ ===
CITIES = {
    "Мюнхен": "https://munich.pasport.org.ua/solutions/e-queue",
    "Берлін": "https://berlin.pasport.org.ua/solutions/e-queue",
    "Прага": "https://prague.pasport.org.ua/solutions/e-queue",
    "Варшава": "https://warsaw.pasport.org.ua/solutions/e-queue",
}

CITY_EMOJI = {"Мюнхен": "🟢", "Берлін": "🔵", "Прага": "🟣", "Варшава": "🟠"}

CHECK_INTERVAL = 35

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

user_city: dict[int, str] = {}
last_status: dict[tuple[int, str], bool] = {}
active_monitoring: dict[int, bool] = {}
debug_checks: list = []


def init_db():
    with sqlite3.connect("slots.db") as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS slots (
                        id INTEGER PRIMARY KEY,
                        city TEXT,
                        chat_id INTEGER,
                        opened_at TEXT,
                        closed_at TEXT,
                        duration_min REAL,
                        weekday INTEGER,
                        hour INTEGER)""")

def main_menu():
    keyboard = [
        ["🔄 Статус", "🏙 Змінити місто"],
        ["⛔ Зупинити", "▶️ Увімкнути"],
        ["📊 Статистика", "🕓 Останній термін"],
        ["🛠 Debug"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def check_slots(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    if not active_monitoring.get(chat_id, False):
        return

    city = user_city.get(chat_id, "Мюнхен")
    url = CITIES[city]
    emoji = CITY_EMOJI[city]

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(user_agent=USER_AGENT)
            page = await ctx.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)

            content = (await page.content()).lower()
            slots_available = "наразі всі місця зайняті" not in content

            await browser.close()

        debug_checks.append({"time": datetime.now().strftime("%H:%M:%S"), "city": city, "available": slots_available})
        if len(debug_checks) > 10:
            debug_checks.pop(0)

        key = (chat_id, city)

        if slots_available and not last_status.get(key, False):
            last_status[key] = True
            now = datetime.now()
            with sqlite3.connect("slots.db") as conn:
                conn.execute("INSERT INTO slots (city, chat_id, opened_at, weekday, hour) VALUES (?,?,?,?,?)",
                             (city, chat_id, now.isoformat(), now.weekday(), now.hour))

            msg = f"{emoji} <b>{city.upper()}</b> — З'ЯВИЛИСЬ ВІЛЬНІ ТЕРМІНИ!"
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Перейти", url=url)]])
            await context.bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode='HTML')

        elif not slots_available and last_status.get(key, False):
            last_status[key] = False
            # закриття терміну в БД (можна розширити)

    except Exception as e:
        logging.error(f"Playwright error {city}: {e}")


# ==================== HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_city[chat_id] = user_city.get(chat_id, "Мюнхен")
    active_monitoring[chat_id] = True

    await update.message.reply_text("✅ Моніторинг запущено!", reply_markup=main_menu())
    context.job_queue.run_repeating(check_slots, interval=CHECK_INTERVAL, first=10, chat_id=chat_id, name=str(chat_id))


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    if text in ["⛔ Зупинити", "Зупинити"]:
        active_monitoring[chat_id] = False
        await update.message.reply_text("⛔ Моніторинг зупинено", reply_markup=main_menu())

    elif text in ["▶️ Увімкнути", "Увімкнути"]:
        active_monitoring[chat_id] = True
        context.job_queue.run_repeating(check_slots, interval=CHECK_INTERVAL, first=10, chat_id=chat_id, name=str(chat_id))
        await update.message.reply_text("▶️ Моніторинг увімкнено", reply_markup=main_menu())

    elif text in CITIES:
        user_city[chat_id] = text
        await update.message.reply_text(f"Місто змінено на: {text}", reply_markup=main_menu())

    elif text == "🏙 Змінити місто":
        await update.message.reply_text("Оберіть місто:", reply_markup=ReplyKeyboardMarkup([[c] for c in CITIES.keys()], resize_keyboard=True))

    elif text == "🛠 Debug":
        await update.message.reply_text(f"Debug:\n{debug_checks[-8:]}", reply_markup=main_menu())


def main():
    init_db()
    app = ApplicationBuilder().token("8713421271:AAExnQzvDRO1BBRHKTFVnpXjwfJN580xNus").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))

    print("Бот запущений...")
    app.run_polling()


if __name__ == "__main__":
    main()
