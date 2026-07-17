import logging
import asyncio
from datetime import datetime

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
TOKEN = "8713421271:AAExnQzvDRO1BBRHKTFVnpXjwfJN580xNus"   # Твой токен

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====================== ХЕНДЛЕРЫ ======================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    
    await update.message.reply_text(
        "👋 Привет! Я готов к работе.\n"
        "Напиши /menu или просто «меню», чтобы открыть главное меню."
    )


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главный обработчик текстовых сообщений"""
    # ЗАЩИТА ОТ ОШИБКИ, КОТОРАЯ БЫЛА В ЛОГАХ
    if update.message is None or update.message.text is None:
        return

    text = update.message.text.strip().lower()

    if text in ["меню", "menu", "/menu", "start"]:
        await show_main_menu(update, context)
    else:
        await update.message.reply_text("Используй команду /menu")


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает главное меню с кнопками"""
    keyboard = [
        [InlineKeyboardButton("🔥 Авантюрное наслаждение", callback_data="aventura")],
        [InlineKeyboardButton("🍀 Плодотворная удача", callback_data="luck")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.edit_text("Выберите действие:", reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на inline-кнопки"""
    query = update.callback_query
    await query.answer()  # убираем "часики" у кнопки

    if query.data == "aventura":
        await query.message.reply_text("🎲 Режим 'Авантюрное наслаждение' активирован!")
    elif query.data == "luck":
        await query.message.reply_text("🍀 Режим 'Плодотворная удача' активирован!")
    elif query.data == "settings":
        await query.message.reply_text("⚙️ Настройки пока в разработке.")
    elif query.data == "info":
        await query.message.reply_text(f"🕒 Текущее время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# ====================== ОСНОВНАЯ ФУНКЦИЯ ======================
async def main():
    application = Application.builder().token(TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("menu", menu_handler))

    # Текстовые сообщения
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            menu_handler
        )
    )

    # Кнопки
    application.add_handler(CallbackQueryHandler(button_handler))

    # Запуск бота
    logger.info("Бот запущен...")
    await application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
