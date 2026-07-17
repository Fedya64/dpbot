import logging
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ====================== НАСТРОЙКИ ======================
TOKEN = "8713421271:AAExnQzvDRO1BBRHKTFVnpXjwfJN580xNus"
TIMEZONE = "Europe/Kiev"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def get_now():
    return datetime.now(ZoneInfo(TIMEZONE))


# ====================== ХЕНДЛЕРЫ ======================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await show_main_menu(update, context)


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
        text = update.message.text.strip().lower()
        if text in ["меню", "/menu", "start"]:
            await show_main_menu(update, context)
        else:
            now = get_now()
            await update.message.reply_text(f"🕒 {now.strftime('%H:%M')}")


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔄 Статус", callback_data="status")],
        [InlineKeyboardButton("🏙 Змінити місто", callback_data="change_city")],
        [InlineKeyboardButton("📊 Статистика термінів", callback_data="stats")],
        [InlineKeyboardButton("⏰ Останній термін", callback_data="last_term")],
        [InlineKeyboardButton("📈 Середня тривалість", callback_data="avg_duration")],
        [InlineKeyboardButton("📅 Найчастіший день", callback_data="popular_day")],
        [InlineKeyboardButton("🕒 Пікова година", callback_data="peak_hour")],
        [InlineKeyboardButton("🛠 Debug", callback_data="debug")],
        [InlineKeyboardButton("⛔ Зупинити моніторинг", callback_data="stop_monitoring")],
        [InlineKeyboardButton("▶ Увімкнути моніторинг", callback_data="start_monitoring")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    now = get_now()
    await update.message.reply_text(
        f"Монітор вільних термінів\n🕒 {now.strftime('%H:%M')}", 
        reply_markup=reply_markup
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    now = get_now()

    if query.data == "status":
        await query.message.reply_text(f"🔴 Мюнхен — unknown state\n🕒 {now.strftime('%H:%M:%S')}")
    elif query.data == "start_monitoring":
        await query.message.reply_text("✅ Моніторинг активований")
    elif query.data == "stop_monitoring":
        await query.message.reply_text("⛔ Моніторинг зупинено")
    elif query.data == "debug":
        await query.message.reply_text(f"Debug info\nTime: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        await query.message.reply_text(f"Функція в розробці\n🕒 {now.strftime('%H:%M')}")


# ====================== ЗАПУСК ======================
async def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info(f"Бот запущен | Таймзона: {TIMEZONE}")
    await application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
