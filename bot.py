import logging
import sqlite3
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ==================== НАЛАШТУВАННЯ ====================
CITIES = {
    "Мюнхен": "https://munich.pasport.org.ua/solutions/e-queue",
    "Берлін": "https://berlin.pasport.org.ua/solutions/e-queue",
    "Прага": "https://prague.pasport.org.ua/solutions/e-queue",
    "Варшава": "https://warsaw.pasport.org.ua/solutions/e-queue",
}

CITY_EMOJI = {"Мюнхен": "🟢", "Берлін": "🔵", "Прага": "🟣", "Варшава": "🟠"}

CHECK_INTERVAL = 45

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# Глобальні дані
user_city: dict[int, str] = {}
last_status: dict[tuple[int, str], bool] = {}
active_monitoring: dict[int, bool] = {}
debug_checks: list = []

# Playwright
playwright_instance = None
browser = None
browser_context = None


def init_db():
    with sqlite3.connect("slots.db") as conn:
        conn.execute("""
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
        """)


def main_menu():
    keyboard = [
        ["🔄 Статус", "🏙 Змінити місто"],
        ["⛔ Зупинити", "▶️ Увімкнути"],
        ["📊 Статистика", "🕓 Останній термін"],
        ["🛠 Debug"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ==================== PLAYWRIGHT ====================
async def init_browser():
    global playwright_instance, browser, browser_context
    try:
        if browser:
            await close_browser()
        playwright_instance = await async_playwright().start()
        browser = await playwright_instance.chromium.launch(headless=True)
        browser_context = await browser.new_context(user_agent=USER_AGENT)
        logging.info("✅ Playwright браузер запущений")
    except Exception as e:
        logging.error(f"❌ Помилка запуску браузера: {e}")


async def close_browser():
    global playwright_instance, browser
    try:
        if browser:
            await browser.close()
        if playwright_instance:
            await playwright_instance.stop()
        logging.info("Браузер закрито")
    except Exception as e:
        logging.error(f"Помилка закриття браузера: {e}")


# ==================== ПЕРЕВІРКА СЛОТІВ ====================
async def check_slots(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    if not active_monitoring.get(chat_id, False):
        return

    city = user_city.get(chat_id, "Мюнхен")
    url = CITIES.get(city)
    if not url or browser_context is None:
        await init_browser()
        return

    emoji = CITY_EMOJI.get(city, "📍")

    try:
        page = await browser_context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=45000)
            content = (await page.content()).lower()

            # === ФІНАЛЬНА ЛОГІКА НА ОСНОВІ ТВОЇХ СКРІНШОТІВ ===
            busy_message = "наразі всі місця зайняті" in content
            has_continue_button = "продовжити" in content
            has_form = "прізвище" in content and "номер телефону" in content

            slots_available = (has_continue_button or has_form) and not busy_message

        finally:
            await page.close()

        # Debug
        debug_checks.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "city": city,
            "available": slots_available,
            "reason": "busy message" if busy_message else "form detected"
        })
        if len(debug_checks) > 15:
            debug_checks.pop(0)

        key = (chat_id, city)

        # Перший запуск — тільки запам'ятовуємо
        if key not in last_status:
            last_status[key] = slots_available
            return

        # З'явились місця
        if slots_available and not last_status.get(key, False):
            last_status[key] = True
            now = datetime.now()
            with sqlite3.connect("slots.db") as conn:
                conn.execute(
                    "INSERT INTO slots (city, chat_id, opened_at, weekday, hour) VALUES (?,?,?,?,?)",
                    (city, chat_id, now.isoformat(), now.weekday(), now.hour)
                )
                conn.commit()

            msg = f"{emoji} <b>{city.upper()}</b> — З'ЯВИЛИСЬ ВІЛЬНІ ТЕРМІНИ!\n\n🔗 Натисніть для запису:"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Перейти до запису", url=url)]])
            try:
                await context.bot.send_message(chat_id, msg, reply_markup=kb, parse_mode='HTML')
            except Exception as e:
                logging.error(f"Send error: {e}")

        # Місця зникли
        elif not slots_available and last_status.get(key, False):
            last_status[key] = False
            with sqlite3.connect("slots.db") as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, opened_at FROM slots 
                    WHERE city = ? AND chat_id = ? AND closed_at IS NULL 
                    ORDER BY id DESC LIMIT 1
                """, (city, chat_id))
                row = cur.fetchone()
                if row:
                    slot_id, opened_at = row
                    duration = (datetime.now() - datetime.fromisoformat(opened_at)).total_seconds() / 60.0
                    cur.execute(
                        "UPDATE slots SET closed_at = ?, duration_min = ? WHERE id = ?",
                        (datetime.now().isoformat(), duration, slot_id)
                    )
                    conn.commit()

    except Exception as e:
        logging.error(f"Check error {city}: {e}")
        debug_checks.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "city": city,
            "available": False,
            "reason": f"ERROR: {str(e)[:80]}"
        })


# ==================== HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_city.setdefault(chat_id, "Мюнхен")
    active_monitoring[chat_id] = True

    for job in context.job_queue.get_jobs_by_name(str(chat_id)):
        job.schedule_removal()

    context.job_queue.run_repeating(
        check_slots, interval=CHECK_INTERVAL, first=10, chat_id=chat_id, name=str(chat_id)
    )

    await update.message.reply_text("✅ Моніторинг запущено!", reply_markup=main_menu())


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    if text == "🔄 Статус":
        status = "🟢 Активний" if active_monitoring.get(chat_id, False) else "🔴 Вимкнений"
        city = user_city.get(chat_id, "Не вибрано")
        await update.message.reply_text(f"Статус: {status}\nМісто: {city}", reply_markup=main_menu())

    elif text == "⛔ Зупинити":
        active_monitoring[chat_id] = False
        for job in context.job_queue.get_jobs_by_name(str(chat_id)):
            job.schedule_removal()
        await update.message.reply_text("⛔ Моніторинг зупинено.", reply_markup=main_menu())

    elif text == "▶️ Увімкнути":
        active_monitoring[chat_id] = True
        for job in context.job_queue.get_jobs_by_name(str(chat_id)):
            job.schedule_removal()
        context.job_queue.run_repeating(check_slots, interval=CHECK_INTERVAL, first=10, chat_id=chat_id, name=str(chat_id))
        await update.message.reply_text("▶️ Моніторинг увімкнено.", reply_markup=main_menu())

    elif text == "🏙 Змінити місто":
        await update.message.reply_text("Оберіть місто:", reply_markup=ReplyKeyboardMarkup([[c] for c in CITIES.keys()], resize_keyboard=True))

    elif text in CITIES:
        old_city = user_city.get(chat_id)
        if old_city:
            last_status.pop((chat_id, old_city), None)
        user_city[chat_id] = text
        last_status[(chat_id, text)] = None
        await update.message.reply_text(f"✅ Місто змінено на: <b>{text}</b>", parse_mode='HTML', reply_markup=main_menu())

    elif text == "📊 Статистика":
        with sqlite3.connect("slots.db") as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*), ROUND(AVG(duration_min),1) FROM slots WHERE chat_id = ? AND closed_at IS NOT NULL", (chat_id,))
            row = cur.fetchone()
        avg = row[1] if row and row[1] else 0
        await update.message.reply_text(f"Закрито термінів: {row[0] if row else 0}\nСередня тривалість: {avg} хв", reply_markup=main_menu())

    elif text == "🕓 Останній термін":
        with sqlite3.connect("slots.db") as conn:
            cur = conn.cursor()
            cur.execute("SELECT city, opened_at, closed_at, duration_min FROM slots WHERE chat_id = ? ORDER BY opened_at DESC LIMIT 1", (chat_id,))
            row = cur.fetchone()
        if row:
            duration = row[3] if row[3] is not None else 0
            await update.message.reply_text(f"Останній: {row[0]} — {duration:.1f} хв", reply_markup=main_menu())
        else:
            await update.message.reply_text("Даних поки немає.", reply_markup=main_menu())

    elif text == "🛠 Debug":
        lines = [f"{x['time']} {'🟢' if x['available'] else '🔴'} {x['city']} — {x['reason']}" for x in debug_checks[-12:]]
        await update.message.reply_text("\n".join(lines) or "Поки немає даних", reply_markup=main_menu())


async def post_init(app):
    await init_browser()


async def post_shutdown(app):
    await close_browser()


def main():
    init_db()
    app = (
        ApplicationBuilder()
        .token("8713421271:AAExnQzvDRO1BBRHKTFVnpXjwfJN580xNus")
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))

    print("Бот запущений...")
    app.run_polling()


if __name__ == "__main__":
    main()
