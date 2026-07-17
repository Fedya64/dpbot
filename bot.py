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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================

def get_now():
    """Текущее время по Киеву."""
    return datetime.now(TZ)


# ====================== МЕНЮ ======================

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["🔄 Статус", "🏙 Змінити місто"],
        ["📊 Статистика термінів", "⏰ Останній термін"],
        ["📈 Середня тривалість", "📅 Найчастіший день"],
        ["🕒 Пікова година", "🛠 Debug"],
        ["⛔ Зупинити моніторинг", "▶ Увімкнути моніторинг"],
    ]

    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )

    now = get_now()

    await update.message.reply_text(
        f"Монітор вільних термінів\n"
        f"🕒 {now.strftime('%H:%M')}",
        reply_markup=reply_markup,
    )


# ====================== КОМАНДЫ ======================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)


# ====================== ОБРАБОТКА ТЕКСТА ======================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text.strip()
    text_lower = text.lower()

    if text_lower in ("меню", "/menu", "start"):
        await show_main_menu(update, context)
        return

    now = get_now()

    match text:

        case "🔄 Статус":
            await update.message.reply_text(
                f"🔴 Мюнхен — unknown state\n"
                f"🕒 {now.strftime('%H:%M:%S')}"
            )

        case "▶ Увімкнути моніторинг":
            await update.message.reply_text(
                "✅ Моніторинг активований"
            )

        case "⛔ Зупинити моніторинг":
            await update.message.reply_text(
                "⛔ Моніторинг зупинено"
            )

        case "🛠 Debug":
            await update.message.reply_text(
                "Debug info\n"
                f"Time: {now.strftime('%Y-%m-%d %H:%M:%S')}"
            )

        case "🏙 Змінити місто":
            await update.message.reply_text(
                "Функція зміни міста поки що в розробці."
            )

        case "📊 Статистика термінів":
            await update.message.reply_text(
                "Статистика поки недоступна."
            )

        case "⏰ Останній термін":
            await update.message.reply_text(
                "Останній знайдений термін відсутній."
            )

        case "📈 Середня тривалість":
            await update.message.reply_text(
                "Недостатньо даних."
            )

        case "📅 Найчастіший день":
            await update.message.reply_text(
                "Недостатньо даних."
            )

        case "🕒 Пікова година":
            await update.message.reply_text(
                "Недостатньо даних."
            )

        case _:
            await update.message.reply_text(
                f"Невідома команда.\n"
                f"Напишіть «меню» або натисніть кнопку.\n"
                f"🕒 {now.strftime('%H:%M')}"
            )


# ====================== ЗАПУСК ======================

def main():

    application = Application.builder().token(TOKEN).build()

    application.add_handler(
        CommandHandler("start", start_command)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler,
        )
    )

    logger.info(
        "Бот запущен | Таймзона: %s",
        TIMEZONE,
    )

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
