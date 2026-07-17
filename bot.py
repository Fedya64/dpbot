import os
import logging
import requests
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

# === ЛОГИ ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# === НАСТРОЙКИ ===
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

CHECK_INTERVAL = 30  # секунд

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Глобальные данные
user_city: dict[int, str] = {}
last_status: dict[tuple[int, str], bool] = {}
active_monitoring: dict[int, bool] = {}
debug_checks: list[dict] = []


# === БАЗА ДАННЫХ ===
def init_db() -> None:
    with sqlite3.connect("slots.db") as conn:
        cur = conn.cursor()
        cur.execute("""
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
        conn.commit()


# === КЛАВИАТУРЫ ===
def main_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        ["🔄 Статус", "🏙 Змінити місто"],
        ["⛔ Зупинити моніторинг", "▶️ Увімкнути моніторинг"],
        ["📊 Статистика термінів"],
        ["🕓 Останній термін", "⏱ Середня тривалість"],
        ["📅 Найчастіший день", "⏰ Пікова година"],
        ["🛠 Debug"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def cities_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[city] for city in CITIES.keys()], resize_keyboard=True)


# === ПРОВЕРКА СЛОТОВ ===
async def check_slots(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.chat_id
    if not active_monitoring.get(chat_id, False):
        return

    city = user_city.get(chat_id, "Мюнхен")
    url = CITIES[city]
    emoji = CITY_EMOJI[city]

    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
        
        if r.status_code != 200:
            slots_available = False
        else:
            soup = BeautifulSoup(r.text, "html.parser")
            page_text = soup.get_text(separator=" ").lower()
            blocked = ["наразі всі місця зайняті", "cloudflare", "attention required", "error"]
            slots_available = not any(word in page_text for word in blocked)

        # Debug info
        debug_checks.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "city": city,
            "available": slots_available,
        })
        if len(debug_checks) > 10:
            debug_checks.pop(0)

        key = (chat_id, city)

        if slots_available and not last_status.get(key, False):
            last_status[key] = True
            now = datetime.now()
            with sqlite3.connect("slots.db") as conn:
                conn.execute(
                    "INSERT INTO slots (city, chat_id, opened_at, weekday, hour) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (city, chat_id, now.isoformat(), now.weekday(), now.hour)
                )
                conn.commit()

            msg = f"{emoji} <b>{city.upper()}</b> — З'ЯВИЛИСЬ ВІЛЬНІ ТЕРМІНИ!\n\n🔗 Натисніть для запису:"
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Перейти до запису", url=url)]])
            await context.bot.send_message(chat_id=chat_id, text=msg, reply_markup=keyboard, parse_mode="HTML")

        elif not slots_available and last_status.get(key, False):
            last_status[key] = False
            with sqlite3.connect("slots.db") as conn:
                cur = conn.cursor()
                cur.execute(
                    """SELECT id, opened_at FROM slots 
                       WHERE city = ? AND chat_id = ? AND closed_at IS NULL 
                       ORDER BY id DESC LIMIT 1""",
                    (city, chat_id)
                )
                row = cur.fetchone()
                if row:
                    slot_id, opened_at = row
                    opened_dt = datetime.fromisoformat(opened_at)
                    duration = (datetime.now() - opened_dt).total_seconds() / 60.0
                    cur.execute(
                        "UPDATE slots SET closed_at = ?, duration_min = ? WHERE id = ?",
                        (datetime.now().isoformat(), duration, slot_id)
                    )
                    conn.commit()

    except Exception as e:
        logging.error(f"Ошибка проверки {city} для {chat_id}: {e}")


# === УПРАВЛЕНИЕ JOB'АМИ ===
def _ensure_single_job(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    for job in jobs:
        job.schedule_removal()


def _start_monitoring(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    _ensure_single_job(context, chat_id)
    context.job_queue.run_repeating(
        check_slots,
        interval=CHECK_INTERVAL,
        first=5,
        chat_id=chat_id,
        name=str(chat_id)
    )


# === КОМАНДЫ И ОБРАБОТЧИКИ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_city.setdefault(chat_id, "Мюнхен")
    active_monitoring[chat_id] = True

    await update.message.reply_text(
        "✅ Моніторинг запущено!\n\nОберіть місто або використовуйте меню.",
        reply_markup=main_menu()
    )
    _start_monitoring(context, chat_id)


async def stop_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    active_monitoring[chat_id] = False
    _ensure_single_job(context, chat_id)
    last_status.pop((chat_id, user_city.get(chat_id)), None)

    await update.message.reply_text("⛔ Моніторинг зупинено.", reply_markup=main_menu())


async def change_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Оберіть місто:", reply_markup=cities_keyboard())


async def set_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    city = update.message.text

    if city in CITIES:
        old_city = user_city.get(chat_id)
        if old_city:
            last_status.pop((chat_id, old_city), None)
        
        user_city[chat_id] = city
        last_status[(chat_id, city)] = False

        await update.message.reply_text(f"🏙 Місто змінено на: <b>{city}</b>", parse_mode="HTML", reply_markup=main_menu())


async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    with sqlite3.connect("slots.db") as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) as total,
                   ROUND(AVG(duration_min), 1) as avg_duration,
                   MAX(duration_min) as max_duration
            FROM slots WHERE chat_id = ? AND closed_at IS NOT NULL
        """, (chat_id,))
        row = cur.fetchone()

    if not row or row[0] == 0:
        text = "📊 Статистики поки немає."
    else:
        text = f"📊 <b>Статистика</b>\n\n"
        text += f"Закритих термінів: <b>{row[0]}</b>\n"
        text += f"Середня тривалість: <b>{row[1]}</b> хв\n"
        text += f"Максимальна: <b>{row[2]}</b> хв"

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_menu())


async def last_term(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    with sqlite3.connect("slots.db") as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT city, opened_at, closed_at, duration_min 
            FROM slots WHERE chat_id = ? 
            ORDER BY opened_at DESC LIMIT 1
        """, (chat_id,))
        row = cur.fetchone()

    if row:
        opened = datetime.fromisoformat(row[1]).strftime("%d.%m %H:%M")
        closed = datetime.fromisoformat(row[2]).strftime("%H:%M") if row[2] else "триває"
        text = f"🕓 <b>Останній термін</b>\n\nМісто: {row[0]}\nВідкрився: {opened}\nЗакрився: {closed}"
        if row[3]:
            text += f"\nТривалість: {row[3]:.1f} хв"
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_menu())
    else:
        await update.message.reply_text("Ще немає даних.", reply_markup=main_menu())


async def debug_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    city = user_city.get(chat_id, "Мюнхен")
    status = "🟢 Активний" if active_monitoring.get(chat_id, False) else "⛔ Вимкнений"

    text = f"<b>Debug Info</b>\n\nМісто: {city}\nСтатус: {status}\nІнтервал: {CHECK_INTERVAL} сек\n\n"
    text += "<b>Останні перевірки:</b>\n"
    for check in reversed(debug_checks[-8:]):
        emoji = "🟢" if check["available"] else "🔴"
        text += f"{check['time']} {emoji} {check['city']}\n"

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_menu())


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()

    if text in ["⛔ Зупинити моніторинг", "Зупинити моніторинг"]:
        return await stop_monitoring(update, context)

    if text in ["▶️ Увімкнути моніторинг", "Увімкнути моніторинг"]:
        chat_id = update.effective_chat.id
        active_monitoring[chat_id] = True
        _start_monitoring(context, chat_id)
        return await update.message.reply_text("▶️ Моніторинг увімкнено.", reply_markup=main_menu())

    if text in ["🔄 Статус", "Статус"]:
        state = "🟢 Активний" if active_monitoring.get(update.effective_chat.id, False) else "⛔ Вимкнений"
        return await update.message.reply_text(f"Статус моніторингу: {state}", reply_markup=main_menu())

    if text in ["🏙 Змінити місто", "Змінити місто"]:
        return await change_city(update, context)

    if text in CITIES:
        return await set_city(update, context)

    if text in ["📊 Статистика термінів", "Статистика термінів"]:
        return await show_statistics(update, context)

    if text in ["🕓 Останній термін", "Останній термін"]:
        return await last_term(update, context)

    if text == "🛠 Debug":
        return await debug_info(update, context)

    await update.message.reply_text("Оберіть дію з меню 👇", reply_markup=main_menu())


# === ЗАПУСК ===
def main() -> None:
    init_db()
    app = ApplicationBuilder().token("8713421271:AAExnQzvDRO1BBRHKTFVnpXjwfJN580xNus").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
