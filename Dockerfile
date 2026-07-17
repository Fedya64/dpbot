import logging
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo   # Рекомендуемый способ в Python 3.9+

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

# ←←← УКАЖИ СВОЮ ВРЕМЕННУЮ ЗОНУ
TIMEZONE = "Europe/Kiev"        # Для Украины
# TIMEZONE = "Europe/Warsaw"    # Для Польши
# TIMEZONE = "Europe/Berlin"    # Для Германии
# TIMEZONE = "Europe/Moscow"    # Для Москвы

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def get_now():
    """Возвращает текущее время в правильной зоне"""
    return datetime.now(ZoneInfo(TIMEZONE))


# ====================== ХЕНДЛЕРЫ ======================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    now = get_now()
    await update.message.reply_text(
        f"👋 Привет! Я готов.\n"
        f"Текущее время: {now.strftime('%H:%M')}\n"
        f"Напиши /menu"
    )


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.text is None:
        return

    text = update.message.text.strip().lower()

    if text in ["меню", "menu", "/menu", "start"]:
        await show_main_menu(update, context)
    else:
        now = get_now()
        await update.message.reply_text(f"Текущее время: {now.strftime('%H:%M')}\nИспользуй /menu")


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔥 Авантюрное наслаждение", callback_data="aventura")],
        [InlineKeyboardButton("🍀 Плодотворная удача", callback_data="luck")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    now = get_now()
    text = f"Выберите действие:\n🕒 Сейчас: {now.strftime('%H:%M')}"

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    now = get_now()

    if query.data == "aventura":
        await query.message.reply_text(f"🎲 Авантюрное наслаждение активировано!\n🕒 {now.strftime('%H:%M')}")
    elif query.data == "luck":
        await query.message.reply_text(f"🍀 Плодотворная удача активирована!\n🕒 {now.strftime('%H:%M')}")
    elif query.data == "info":
        await query.message.reply_text(f"🕒 Текущее время: {now.strftime('%Y-%m-%d %H:%M:%S')}")


# ====================== ЗАПУСК ======================
async def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("menu", menu_handler))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler)
    )
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info(f"Бот запущен. Таймзона: {TIMEZONE}")
    await application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
