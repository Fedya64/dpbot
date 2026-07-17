import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ====================== НАСТРОЙКИ ======================

TOKEN = "8713421271:AAExnQzvDRO1BBRHKTFVnpXjwfJN580xNus"
TIMEZONE = "Europe/Kyiv"
TZ = ZoneInfo(TIMEZONE)

CITIES = ["Мюнхен", "Берлін", "Прага", "Варшава"]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================

def get_now():
    return datetime.now(TZ)


# ====================== МЕНЮ ======================

def build_keyboard():
    keyboard = [
        ["▶ Увімкнути моніторинг", "⛔ Зупинити моніторинг"],
        ["🏙 Змінити місто", "📍 Поточне місто"],
        ["🔄 Статус"],
        ["📊 Статистика термінів"],
        ["⏰ Останній термін"],
        ["🕒 Пікова година"],
        ["🛠 Debug"],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def build_city_keyboard():
    keyboard = [[city] for city in CITIES]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=True
    )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = get_now()
    await update.message.reply_text(
        f"Монітор вільних термінів\n🕒 {now.strftime('%H:%M')}",
        reply_markup=build_keyboard(),
    )


# ====================== КОМАНДЫ ======================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = get_now()
    context.user_data["city"] = "Мюнхен"
    await update.message.reply_text(
        f"📍 Місто: {context.user_data['city']}\n"
        f"🟢 Моніторинг активний\n"
        f"🎁 Безкоштовні сповіщення: необмежено\n\n"
        f"Я повідомлю, коли з’являться вільні слоти.\n"
        f"🕒 {now.strftime('%H:%M')}"
    )
    await show_main_menu(update, context)


# ====================== ОБРАБОТКА ТЕКСТА ======================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    now = get_now()

    if text == "🏙 Змінити місто":
        await update.message.reply_text(
            "Оберіть місто:",
            reply_markup=build_city_keyboard()
        )
        return

    if text in CITIES:
        context.user_data["city"] = text
        await update.message.reply_text(
            f"🏙 Місто змінено на: {text}",
            reply_markup=build_keyboard()
        )
        return

    match text:
        case "📍 Поточне місто":
            city = context.user_data.get("city", "Мюнхен")
            await update.message.reply_text(f"📍 Поточне місто: {city}")
        case "🔄 Статус":
            city = context.user_data.get("city", "Мюнхен")
            await update.message.reply_text(
                f"🔴 {city} — unknown state\n🕒 {now.strftime('%H:%M:%S')}"
            )
        case "▶ Увімкнути моніторинг":
            await update.message.reply_text("✅ Моніторинг активований")
        case "⛔ Зупинити моніторинг":
            await update.message.reply_text("⛔ Моніторинг зупинено")
        case "🛠 Debug":
            await update.message.reply_text(
                "Debug info\n"
                f"Time: {now.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        case "📊 Статистика термінів":
            await update.message.reply_text("Статистика поки недоступна.")
        case "⏰ Останній термін":
            await update.message.reply_text("Останній знайдений термін відсутній.")
        case "🕒 Пікова година":
            await update.message.reply_text("Недостатньо даних.")
        case _:
            await update.message.reply_text(
                f"Невідома команда.\n"
                f"Напишіть «меню» або натисніть кнопку.\n"
                f"🕒 {now.strftime('%H:%M')}"
            )


# ====================== ЗАПУСК ======================

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("Бот запущен | Таймзона: %s", TIMEZONE)
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
