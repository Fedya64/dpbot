import os
import sys
import logging
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    PicklePersistence,
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

            logger.info("Перевірка сайту для міста: %s", city)

            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            
            text = (await page.inner_text("body")).lower()

            if "наразі всі місця зайняті" in text:
                logger.info("Термінів немає: %s", city)
                return False, f"❌ {city}: термінів немає"

            elif "продовжити" in text:
                logger.info("Знайдено вільні терміни: %s", city)
                return True, f"✅ {city}: є вільні терміни!"

            logger.info("Ключові слова не знайдено: %s", city)
            return None, f"⚠️ {city}: сайт доступний, але статус незрозумілий (змінився інтерфейс)"

    except Exception as e:
        logger.exception("Помилка при перевірці %s", city)
        return None, f"❌ Помилка при перевірці {city}: {e}"

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
    if "city" not in context.chat_data:
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
            await update.message.reply_text("⏳ Перевіряю сайт, зачекайте кілька секунд...")
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


# ====================== ОПТИМИЗИРОВАННЫЙ МОНИТОРИНГ ======================

async def monitor_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Проверяет каждый город ровно 1 раз параллельно, 
    после чего рассылает результаты нужным пользователям.
    """
    application = context.application
    active_cities = set()

    for chat_id, data in application.chat_data.items():
        if data.get("monitoring", False):
            active_cities.add(data.get("city", "Мюнхен"))

    if not active_cities:
        return

    logger.info(f"Запуск системного мониторинга для городов: {active_cities}")

    tasks = {city: check_slots_playwright(city) for city in active_cities}
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    
    city_states = {}
    for city, res in zip(tasks.keys(), results):
        if isinstance(res, Exception):
            city_states[city] = (None, f"❌ Системна помилка: {res}")
        else:
            city_states[city] = res

    for chat_id, data in application.chat_data.items():
        if data.get("monitoring", False):
            city = data.get("city", "Мюнхен")
            state, result_text = city_states.get(city, (None, None))

            if state is True and not data.get("last_state", False):
                try:
                    await application.bot.send_message(chat_id=chat_id, text=result_text)
                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение {chat_id}: {e}")

            if state is not None:
                data["last_state"] = state


def main():
    if not TOKEN:
        logger.error("КРИТИЧЕСКАЯ ОШИБКА: Токен не задан!")
        sys.exit(1)

    persistence = PicklePersistence(filepath="/app/data/bot_persistence.pickle")

    application = (
        Application.builder()
        .token(TOKEN)
        .persistence(persistence)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .pool_timeout(30)
        .build()
    )

    # Используем стабильный и нативный метод .run_repeating() у встроенного job_queue
    job_queue = application.job_queue
    job_queue.run_repeating(
        monitor_job,
        interval=60,  # Каждые 60 секунд
        first=10,     # Первый запуск через 10 секунд
        name="slots_monitoring_job"
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("Бот запущен | Таймзона: %s", TIMEZONE)
    
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
