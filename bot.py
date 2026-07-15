import os
import time
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackContext,
    MessageHandler, Filters
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

# Збереження міста для кожного користувача
user_city = {}

CHECK_INTERVAL = 30  # секунд


def check_slots(context: CallbackContext):
    chat_id = context.job.context
    city = user_city.get(chat_id, "Мюнхен")
    url = CITIES[city]

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        if "Наразі всі місця зайняті" not in soup.text:
            msg = f"🟢 Є вільні слоти у місті {city}!\nПерейти до запису:\n{url}"
            context.bot.send_message(chat_id=chat_id, text=msg)
            logging.info(f"Слоти знайдено для {city}")
        else:
            logging.info(f"Немає слотів для {city}")

    except Exception as e:
        logging.error(f"Помилка: {e}")


def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    user_city.setdefault(chat_id, "Мюнхен")

    update.message.reply_text(
        f"Моніторинг запущено.\nМісто: {user_city[chat_id]}",
        reply_markup=main_menu()
    )

    context.job_queue.run_repeating(check_slots, CHECK_INTERVAL, context=chat_id)


def stop(update: Update, context: CallbackContext):
    context.job_queue.stop()
    update.message.reply_text("Моніторинг зупинено.", reply_markup=main_menu())


def status(update: Update, context: CallbackContext):
    city = user_city.get(update.message.chat_id, "Мюнхен")
    update.message.reply_text(
        f"Моніторинг активний.\nМісто: {city}",
        reply_markup=main_menu()
    )


def city(update: Update, context: CallbackContext):
    keyboard = [[city] for city in CITIES.keys()]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    update.message.reply_text("Оберіть місто:", reply_markup=reply_markup)


def city_choice(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    choice = update.message.text

    if choice in CITIES:
        user_city[chat_id] = choice
        update.message.reply_text(
            f"Місто змінено на: {choice}",
            reply_markup=main_menu()
        )
    else:
        update.message.reply_text(
            "Невірне місто.\nВикористайте /city щоб обрати.",
            reply_markup=main_menu()
        )


def help_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(
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

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("stop", stop))
    dp.add_handler(CommandHandler("status", status))
    dp.add_handler(CommandHandler("city", city))
    dp.add_handler(CommandHandler("help", help_cmd))

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, city_choice))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
