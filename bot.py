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
        return None, f"❌ Немає сайту для {city}"

    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = await browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/138.0.0.0 Safari/537.36"
                )
            )

            logger.info("Перевірка %s", city)

            await page.goto(url, timeout=30000, wait_until="networkidle")
            text = (await page.inner_text("body")).lower()

            if "наразі всі місця зайняті" in text:
                logger.info("Термінів немає: %s", city)
                return False, f"❌ {city}: термінів немає"

            elif "продовжити" in text:
                logger.info("Знайдено вільні терміни: %s", city)
                return True, f"✅ {city}: є вільні терміни!"

            logger.info("Ключові слова не знайдено: %s", city)
            return None, f"⚠️ {city}: сайт доступний, але ключові слова не знайдено"

    except Exception as e:
        logger.exception("Помилка при перевірці %s", city)
        return None, f"❌ Помилка при перевірці: {e}"

    finally:
        if browser:
            await browser.close()


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
    context.chat_data["city"] = "Мюнхен"
    context.chat_data["monitoring"] = True
    context.chat_data["last_state"] = False
    await update.message.reply_text(
        f"📍 Місто: {context.chat_data['city']}\n"
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
        context.chat_data["city"] = text
        await update.message.reply_text(f"🏙 Місто змінено на: {text}", reply_markup=build_keyboard())
        return

    match text:
        case "📍 Поточне місто":
            city = context.chat_data.get("city", "Мюнхен")
            await update.message.reply_text(f"📍 Поточне місто: {city}")
        case "🔄 Статус":
            city = context.chat_data.get("city", "Мюнхен")
            _, result = await check_slots_playwright(city)
            await update.message.reply_text(result)
        case "▶ Увімкнути моніторинг":
            context.chat_data["monitoring"] = True
            await update.message.reply_text("✅ Моніторинг активований")
        case "⛔ Зупинити моніторинг":
            context.chat_data["monitoring"] = False
            await update.message.reply_text("⛔ Моніторинг зупинено")
        case "🛠 Debug":
            await update.message.reply_text("Debug info: chat_data=" + str(context.chat_data))
        case _:
            await update.message.reply_text("Невідома команда. Натисніть кнопку.")


# ====================== АВТОМАТИЧНИЙ МОНІТОРИНГ ======================

async def monitor_job(application: Application):
    for chat_id, data in application.chat_data.items():
        if data.get("monitoring", False):
            city = data.get("city", "Мюнхен")
            state, result = await check_slots_playwright(city)
            if state and not data.get("last_state", False):
                await application.bot.send_message(chat_id=chat_id, text=result)
            # обновляем только если состояние определено
            if state is not None:
                data["last_state"] = state


def main():
    application = Application.builder().token(TOKEN).build()

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        monitor_job,
        trigger="interval",
        minutes=1,
        args=[application],
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("Бот запущен | Таймзона: %s", TIMEZONE)
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
