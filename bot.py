import os
import time
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)

# === ЛОГУВАННЯ ===
logging.basicConfig(
    filename="log.txt",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

# === МІСТА ===
CITIES = {
    "Мюнхен": "https://munich.pasport.org.ua/solutions/e-queue",
    "Берлін": "https://berlin.pasport.org.ua/solutions/e-queue",
    "Прага": "https://prague.pasport.org.ua/solutions/e-queue",
    "Варшава": "https://warsaw.pasport.org.ua/solutions/e-queue",
}

user_city = {}
CHECK_INTERVAL = 30


async def check_slots(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    city = user_city.get(chat_id, "Мюнхен")
    url = CITIES[city]

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        if "Наразі всі місця зайняті" not in soup.text:
            msg = f"🟢 Є вільні слоти у місті {city}!\nПерейти до запису:\n{url}"
            await context.bot.send_message(chat_id=chat_id, text=msg)
            logging.info(f"Слоти знайдено для {city}")
        else:
            logging.info(f"Немає слотів для {city}")

    except Exception as e:
        logging.error(f"Помилка: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_city.setdefault(chat_id, "Мюнхен")

    await update.message.reply_text(
        f"Моніторинг запущено.\nМісто: {user_city[chat_id]}",
        reply_markup=main_menu()
    )

    context.job_queue.run_repeating(
        check_slots,
        interval=CHECK_INTERVAL,
        first=5,
        chat_id=chat_id
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.job_queue.stop()
    await update.message.reply_text("Моніторинг зупинено.", reply_markup=main_menu())


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = user_city.get(update.effective_chat.id, "Мюнхен")
    await update.message.reply_text(
        f"Моніторинг активний.\nМісто: {city}",
        reply_markup=main_menu()
    )


async def city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[city] for city in CITIES.keys()]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Оберіть місто:", reply_markup=reply_markup)


async def city_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    choice = update.message.text

    if choice in CITIES:
        user_city[chat_id] = choice
        await update.message.reply_text(
            f"Місто змінено на: {choice}",
            reply_markup=main_menu()
        )
    else:
        await update.message.reply_text(
            "Невірне місто.\nВикористайте /city щоб обрати.",
            reply_markup=main_menu()
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start — запустити моніторинг\n"
        "/stop — зупинити моніторинг\n"
        "/status — статус\n"
        "/city — змінити місто\n"
        "/help — допомога",
        reply_markup=main_menu()
    )


def main_menu():
    keyboard = [
        ["Статус", "Змінити місто"],
        ["Зупинити моніторинг"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def main():
    TOKEN = os.getenv("TOKEN")

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("city", city))
    application.add_handler(CommandHandler("help", help_cmd))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, city_choice))

    application.run_polling()


if __name__ == "__main__":
    main()
