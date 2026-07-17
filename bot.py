import logging
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

TIMEZONE = "Europe/Kiev"   # Europe/Kiev, Europe/Warsaw, Europe/Berlin

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
        now = get_now()
        await update.message.reply_text(f"👋 Бот запущен!\n🕒 {now.strftime('%H:%M')}")


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
        text = update.message.text.strip().lower()
        if text in ["меню", "/menu", "start"]:
            await show_main_menu(update, context)
        else:
            now = get_now()
            await update.message.reply_text(f"🕒 Сейчас: {now.strftime('%H:%M')}")


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔥 Авантюрное наслаждение", callback_data="aventura")],
        [InlineKeyboardButton("🍀 Плодотворная удача", callback_data="luck")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    now = get_now()
    await update.message.reply_text(
        f"Главное меню\n🕒 {now.strftime('%H:%M')}", 
        reply_markup=reply_markup
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    now = get_now()

    if query.data == "aventura":
        await query.message.reply_text(f"🎲 Авантюрное наслаждение активировано!\n🕒 {now.strftime('%H:%M')}")
    elif query.data == "luck":
        await query.message.reply_text(f"🍀 Плодотворная удача активирована!\n🕒 {now.strftime('%H:%M')}")
    elif query.data == "settings":
        await query.message.reply_text("⚙️ Настройки пока в разработке.")
    elif query.data == "info":
        await query.message.reply_text(f"🕒 Текущее время: {now.strftime('%Y-%m-%d %H:%M:%S')}")


# ====================== ЗАПУСК ======================
if __name__ == "__main__":
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info(f"Бот запущен | Таймзона: {TIMEZONE}")

    # Исправленный запуск для Railway и подобных платформ
    application.run_polling(drop_pending_updates=True)
