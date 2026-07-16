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
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# === ЛОГИ ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
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

user_city = {}
last_status = {}
active_monitoring = {}
debug_checks = []  # последние 5 проверок

CHECK_INTERVAL = 30


# === БАЗА ДЛЯ СТАТИСТИКИ ===
def init_db():
    conn = sqlite3.connect("slots.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT,
            opened_at TEXT,
            closed_at TEXT,
            duration_min REAL,
            weekday INTEGER,
            hour INTEGER
        )
    """)
    conn.commit()
    conn.close()


# === МЕНЮ ===
def main_menu():
    keyboard = [
        ["🔄 Статус", "🏙 Змінити місто"],
        ["⛔ Зупинити моніторинг", "▶️ Увімкнути моніторинг"],
        ["📊 Статистика термінів"],
        ["🕓 Останній термін"],
        ["⏱ Середня тривалість"],
        ["📅 Найчастіший день"],
        ["⏰ Пікова година"],
        ["🛠 Debug"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# === ПРОВЕРКА СЛОТОВ ===
async def check_slots(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id

    if not active_monitoring.get(chat_id, False):
        return

    city = user_city.get(chat_id, "Мюнхен")
    url = CITIES[city]
    emoji = CITY_EMOJI[city]

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()

        # лог HTML
        with open("last_page.html", "w", encoding="utf-8") as f:
            f.write(r.text)

        soup = BeautifulSoup(r.text, "html.parser")

        # очищенный текст
        page_text = soup.get_text(separator=" ").replace("\n", " ").replace("\r", " ").strip()
        with open("last_text.txt", "w", encoding="utf-8") as f:
            f.write(page_text)

        # детектор отсутствия слотов
        slots_available = "Наразі всі місця зайняті" not in page_text

        # debug лог
        debug_checks.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "city": city,
            "available": slots_available
        })
        if len(debug_checks) > 5:
            debug_checks.pop(0)

        # === СЛОТ ПОЯВИЛСЯ ===
        if slots_available and not last_status.get(city, False):
            last_status[city] = True

            now = datetime.now()

            conn = sqlite3.connect("slots.db")
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO slots (city, opened_at, weekday, hour)
                VALUES (?, ?, ?, ?)
            """, (city, now.isoformat(), now.weekday(), now.hour))
            conn.commit()
            conn.close()

            msg = (
                f"{emoji} {city.upper()} — З'ЯВИЛИСЬ ВІЛЬНІ ТЕРМІНИ!\n"
                f"📅 Паспортний сервіс\n"
                f"🔗 Натисніть, щоб записатися:"
            )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Перейти до запису", url=url)]
            ])

            await context.bot.send_message(chat_id=chat_id, text=msg, reply_markup=keyboard)

        # === СЛОТ ИСЧЕЗ ===
        elif not slots_available and last_status.get(city, False):
            last_status[city] = False

            conn = sqlite3.connect("slots.db")
            cur = conn.cursor()

            cur.execute("""
                SELECT id, opened_at FROM slots
                WHERE city = ? AND closed_at IS NULL
                ORDER BY id DESC LIMIT 1
            """, (city,))
            row = cur.fetchone()

            if row:
                slot_id, opened_at = row
                opened_dt = datetime.fromisoformat(opened_at)
                closed_dt = datetime.now()
                duration = (closed_dt - opened_dt).total_seconds() / 60.0

                cur.execute("""
                    UPDATE slots
                    SET closed_at = ?, duration_min = ?
                    WHERE id = ?
                """, (closed_dt.isoformat(), duration, slot_id))
                conn.commit()

            conn.close()

    except Exception as e:
        logging.error(f"Помилка: {e}")


# === ВКЛЮЧЕНИЕ МОНИТОРИНГА ===
async def enable_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    active_monitoring[chat_id] = True

    await update.message.reply_text(
        "▶️ Моніторинг увімкнено.",
        reply_markup=main_menu()
    )

    context.job_queue.run_repeating(
        check_slots,
        interval=CHECK_INTERVAL,
        first=5,
        chat_id=chat_id,
        name=str(chat_id)
    )


# === ОСТАНОВКА МОНИТОРИНГА ===
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    active_monitoring[chat_id] = False

    await update.message.reply_text(
        "⛔ Моніторинг зупинено.",
        reply_markup=main_menu()
    )


# === СТАРТ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    user_city.setdefault(chat_id, "Мюнхен")
    active_monitoring[chat_id] = True

    msg = (
        f"📍 Місто: {user_city[chat_id]}\n"
        f"🟢 Моніторинг активний\n"
        f"🎁 Безкоштовні сповіщення: необмежено\n\n"
        f"Я повідомлю, коли з’являться вільні слоти."
    )

    await update.message.reply_text(msg, reply_markup=main_menu())

    context.job_queue.run_repeating(
        check_slots,
        interval=CHECK_INTERVAL,
        first=5,
        chat_id=chat_id,
        name=str(chat_id)
    )


# === СТАТУС ===
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    city = user_city.get(chat_id, "Мюнхен")

    state = "🟢 Активний" if active_monitoring.get(chat_id, False) else "⛔ Вимкнений"

    msg = (
        f"📍 Місто: {city}\n"
        f"{state}\n"
        f"🎁 Безкоштовні сповіщення: необмежено"
    )

    await update.message.reply_text(msg, reply_markup=main_menu())


# === СТАТИСТИКА ===
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    city = user_city.get(chat_id, "Мюнхен")

    conn = sqlite3.connect("slots.db")
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM slots WHERE city = ?", (city,))
    count = cur.fetchone()[0]

    cur.execute("SELECT AVG(duration_min) FROM slots WHERE city = ?", (city,))
    avg_duration = cur.fetchone()[0]

    cur.execute("""
        SELECT weekday, COUNT(*) FROM slots
        WHERE city = ?
        GROUP BY weekday
        ORDER BY COUNT(*) DESC
        LIMIT 1
    """, (city,))
    row_day = cur.fetchone()

    cur.execute("""
        SELECT hour, COUNT(*) FROM slots
        WHERE city = ?
        GROUP BY hour
        ORDER BY COUNT(*) DESC
        LIMIT 1
    """, (city,))
    row_hour = cur.fetchone()

    conn.close()

    avg_text = f"{avg_duration:.1f} хв" if avg_duration else "немає даних"

    weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
    day_text = weekday_names[row_day[0]] if row_day else "немає даних"
    hour_text = f"{row_hour[0]}:00" if row_hour else "немає даних"

    msg = (
        f"📊 Статистика появи термінів за {city}:\n"
        f"• Вікон доступності: {count}\n"
        f"• Середня тривалість: {avg_text}\n"
        f"• Найчастіший день: {day_text}\n"
        f"• Пік по годинах: {hour_text}\n"
        f"• Дані збираються автоматично"
    )

    await update.message.reply_text(msg, reply_markup=main_menu())


# === /slotstats ===
async def slotstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    city = user_city.get(chat_id, "Мюнхен")

    conn = sqlite3.connect("slots.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT AVG(duration_min)
        FROM slots
        WHERE city = ? AND duration_min IS NOT NULL
    """, (city,))
    avg_duration = cur.fetchone()[0]
    conn.close()

    if not avg_duration:
        await update.message.reply_text("Поки немає даних про тривалість термінів.")
        return

    msg = (
        f"⏱ Середня тривалість термінів у {city}:\n"
        f"• {avg_duration:.1f} хвилин"
    )

    await update.message.reply_text(msg)


# === /slotday ===
async def slotday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    city = user_city.get(chat_id, "Мюнхен")

    conn = sqlite3.connect("slots.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT weekday, COUNT(*)
        FROM slots
        WHERE city = ?
        GROUP BY weekday
        ORDER BY COUNT(*) DESC
        LIMIT 1
    """, (city,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("Поки немає даних про дні появи термінів.")
        return

    weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
    day_name = weekday_names[row[0]]

    msg = (
        f"📅 Найчастіший день появи термінів у {city}:\n"
        f"• {day_name}"
    )

    await update.message.reply_text(msg)


# === /slothour ===
async def slothour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    city = user_city.get(chat_id, "Мюнхен")

    conn = sqlite3.connect("slots.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT hour, COUNT(*)
        FROM slots
        WHERE city = ?
        GROUP BY hour
        ORDER BY COUNT(*) DESC
        LIMIT 1
    """, (city,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("Поки немає даних про години появи термінів.")
        return

    hour, count = row
    msg = (
        f"⏰ Пікова година появи термінів у {city}:\n"
        f"• {hour}:00\n"
        f"• Кількість появ: {count}"
    )

    await update.message.reply_text(msg)


# === /lastslot ===
async def lastslot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    city = user_city.get(chat_id, "Мюнхен")

    conn = sqlite3.connect("slots.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT opened_at, closed_at, duration_min
        FROM slots
        WHERE city = ?
        ORDER BY id DESC
        LIMIT 1
    """, (city,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("Поки немає жодного зафіксованого терміну.")
        return

    opened_at, closed_at, duration = row

    opened_dt = datetime.fromisoformat(opened_at).strftime("%d.%m %H:%M")
    closed_dt = closed_at and datetime.fromisoformat(closed_at).strftime("%d.%m %H:%M")
    duration_text = f"{duration:.1f} хв" if duration else "невідомо"

    msg = (
        f"🕓 Останній термін у {city}:\n"
        f"• Початок: {opened_dt}\n"
        f"• Кінець: {closed_dt or 'ще триває'}\n"
        f"• Тривалість: {duration_text}"
    )

    await update.message.reply_text(msg)


# === /debug ===
async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not debug_checks:
        await update.message.reply_text("Поки немає даних для debug.")
        return

    msg = "🛠 Останні 5 перевірок:\n\n"
    for item in debug_checks:
        status = "СЛОТИ Є !!!" if item["available"] else "слотів немає"
        msg += f"{item['time']} — {item['city']} — {status}\n"

    await update.message.reply_text(msg)


# === ВЫБОР ГОРОДА ===
async def city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[city] for city in CITIES.keys()]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("🏙 Оберіть місто:", reply_markup=reply_markup)


async def city_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    choice = update.message.text

    if choice in CITIES:
        user_city[chat_id] = choice
        last_status[choice] = False
        await update.message.reply_text(
            f"🏙 Місто змінено на: {choice}",
            reply_markup=main_menu()
        )


# === ОБРАБОТКА МЕНЮ ===
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text in ["🔄 Статус", "Статус"]:
        return await status(update, context)

    if text in ["🏙 Змінити місто", "Змінити місто"]:
        return await city(update, context)

    if text in ["📊 Статистика термінів", "Статистика термінів"]:
        return await stats(update, context)

    if text in ["🕓 Останній термін", "Останній термін"]:
        return await lastslot(update, context)

    if text in ["⏱ Середня тривалість", "Середня тривалість"]:
        return await slotstats(update, context)

    if text in ["📅 Найчастіший день", "Найчастіший день"]:
        return await slotday(update, context)

    if text in ["⏰ Пікова година", "Пікова година"]:
        return await slothour(update, context)

    if text in ["🛠 Debug", "Debug"]:
        return await debug(update, context)

    if text in ["⛔ Зупинити моніторинг", "Зупинити моніторинг"]:
        return await stop(update, context)

    if text in ["▶️ Увімкнути моніторинг", "Увімкнути моніторинг"]:
        return await enable_monitoring(update, context)


# === ЗАПУСК ===
def main():
    TOKEN = os.getenv("TOKEN")
    init_db()

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("city", city))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("slotstats", slotstats))
    application.add_handler(CommandHandler("slotday", slotday))
    application.add_handler(CommandHandler("slothour", slothour))
    application.add_handler(CommandHandler("lastslot", lastslot))
    application.add_handler(CommandHandler("debug", debug))

    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND &
        filters.Regex(
            "^(🔄 Статус|Статус|"
            "🏙 Змінити місто|Змінити місто|"
            "📊 Статистика термінів|Статистика термінів|"
            "🕓 Останній термін|Останній термін|"
            "⏱ Середня тривалість|Середня тривалість|"
            "📅 Найчастіший день|Найчастіший день|"
            "⏰ Пікова година|Пікова година|"
            "🛠 Debug|Debug|"
            "⛔ Зупинити моніторинг|Зупинити моніторинг|"
            "▶️ Увімкнути моніторинг|Увімкнути моніторинг)$"
        ),
        menu_handler
    ))

    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND &
        filters.Regex("^(Мюнхен|Берлін|Прага|Варшава)$"),
        city_choice
    ))

    application.run_polling()


if __name__ == "__main__":
    main()
