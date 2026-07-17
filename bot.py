import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from playwright.async_api import async_playwright

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

CITY_URLS = {
    "Мюнхен": "https://munich.pasport.org.ua/solutions/e-queue",
    "Берлін": "https://berlin.pasport.org.ua/solutions/e-queue",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================

def get_now():
    return datetime.now(TZ)


async def check_slots_playwright(city: str):
    url = CITY_URLS.get(city)
    if not url:
        return f"❌ Немає сайту для {city}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=30000)
            content = await page.content()
            await browser.close()

            text = content.lower()
            # ❌ Нет терминов
            if "наразі всі місця зайняті" in text:
                return f"❌ {city}: термінів немає"
            # ✅ Есть термины
            elif "продовжити" in text:
                return f"✅ {city}: є вільні терміни!"
            else:
                return f"⚠️ {city}: сайт доступний, але ключові слова не знайдено"
    except Exception as e:
        return f"❌ Помилка при перевірці: {e}"


# ====================== МЕНЮ ======================

def build_keyboard():
    keyboard = [
        ["▶ Увімкнути моніторинг", "⛔ Зупинити моніторинг"],
        ["🏙 Змінити місто", "📍 Поточне місто"],
        ["🔄 Статус"],
        ["🛠 Debug"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def build_city_keyboard():
    keyboard = [[city] for city in CITY_URLS.keys()]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


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
    context.user_data["monitoring"] = True
    await update.message.reply_text(
        f"📍 Місто: {context.user_data['city']}\n"
        f"🟢 Моніторинг активний\n"
        f"Я повідомлю, коли з’являться вільні слоти.\n"
        f"🕒 {now.strftime('%H:%M')}"
    )
    await show_main_menu(update, context)


# ====================== ОБРАБОТКА ТЕКСТА ======================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    if text == "🏙 Змінити місто":
        await update.message.reply_text("Оберіть місто:", reply_markup=build_city_keyboard())
        return

    if text in CITY_URLS.keys():
        context.user_data["city"] = text
        await update.message.reply_text(f"🏙 Місто змінено на: {text}", reply_markup=build_keyboard())
        return

    match text:
        case "📍 Поточне місто":
            city = context.user_data.get("city", "Мюнхен")
            await update.message.reply_text(f"📍 Поточне місто: {city}")
        case "🔄 Статус":
            city = context.user_data.get("city", "Мюнхен")
            result = await check_slots_playwright(city)
            await update.message.reply_text(result)
        case "▶ Увімкнути моніторинг":
            context.user_data["monitoring"] = True
            await update.message.reply_text("✅ Моніторинг активований")
        case "⛔ Зупинити моніторинг":
            context.user_data["monitoring"] = False
            await update.message.reply_text("⛔ Моніторинг зупинено")
        case "🛠 Debug":
            await update.message.reply_text("Debug info: user_data=" + str(context.user_data))
        case _:
            await update.message.reply_text("Невідома команда. Натисніть кнопку.")


# ====================== АВТОМАТИЧНИЙ МОНІТОРИНГ ======================

async def monitor_job(application: Application):
    for chat_id, data in application.chat_data.items():
        if data.get("monitoring", False):
            city = data.get("city", "Мюнхен")
            result = await check_slots_playwright(city)
            if "✅" in result:
                await application.bot.send_message(chat_id=chat_id, text=result)


def main():
    application = Application.builder().token(TOKEN).build()

    # планировщик: проверка раз в минуту
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(lambda: monitor_job(application), "interval", minutes=1)
    scheduler.start()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("Бот запущен | Таймзона: %s", TIMEZONE)
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
