import os
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)

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

CITY_EMOJI = {
    "Мюнхен": "🟢",
    "Берлін": "🔵",
    "Прага": "🟣",
    "Варшава": "🟠",
}

user_city = {}
last_status = {}  # анти-спам: True = слоты были, False = не было

CHECK_INTERVAL = 30


def main_menu():
    keyboard = [
        ["🔄 Статус", "🏙 Змінити місто"],
        ["⛔ Зупинити моніторинг"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def check_slots(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    city = user_city.get(chat_id, "Мюнхен")
    url = CITIES[city]
    emoji = CITY_EMOJI[city]

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        slots_available = "Наразі всі місця зайняті" not in soup.text

        # === АНТИ-СПАМ ===
        if slots_available and not last_status.get(city, False):
            last_status[city] = True

            msg = (
                f"{emoji} {city.upper()} — З'ЯВИЛИСЬ ВІЛЬНІ ТЕРМІНИ!\n"
                f"📅 Паспортний сервіс\n"
                f"🔗 Натисніть, щоб записатися:"
            )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Перейти до запису", url=url)]
            ])

            await context.bot.send_message(chat_id=chat_id, text=msg, reply_markup=keyboard)
            logging.info(f"Слоти знайдено для {city}")

        elif not slots_available:
            last_status[city] = False

    except Exception as e:
        logging.error(f"Помилка: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_city.setdefault(chat_id, "Мюнхен")

    msg = (
        f"📍 Місто: {user_city[chat_id]}\n"
        f"🟢 Моніторинг активний\n"
        f"🎁 Безкоштовні сповіщення: необмежено\n\n"
        f"Я повідомлю, коли з’являться вільні слоти у е-черзі Паспортного сервісу."
    )

    await update.message.reply_text(msg, reply_markup=main_menu())

    context.job_queue.run_repeating(
        check_slots,
        interval=CHECK_INTERVAL,
        first=5,
        chat_id=chat_id
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.job_queue.stop()
    await update.message.reply_text(
        "⛔ Моніторинг зупинено.",
        reply_markup=main_menu()
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = user_city.get(update.effective_chat.id, "Мюнхен")
    msg = (
        f"📍 Місто: {city}\n"
        f"🟢 Моніторинг активний\n"
        f"🎁 Безкоштовні сповіщення: необмежено"
    )
    await update.message.reply_text(msg, reply_markup=main_menu())


async def city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[city] for city in CITIES.keys()]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("🏙 Оберіть місто:", reply_markup=reply_markup)


async def city_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    choice = update.message.text

    if choice in CITIES:
        user_city[chat_id] = choice
        last_status[choice] = False  # сбрасываем анти-спам
        await update.message.reply_text(
            f"🏙 Місто змінено на: {choice}",
            reply_markup=main_menu()
        )


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🔄 Статус":
        return await status(update, context)

    if text == "🏙 Змінити місто":
        return await city(update, context)

    if text == "⛔ Зупинити моніторинг":
        return await stop(update, context)


def main():
    TOKEN = os.getenv("TOKEN")
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("city", city))

    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND &
        filters.Regex("^(🔄 Статус|🏙 Змінити місто|⛔ Зупинити моніторинг)$"),
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
