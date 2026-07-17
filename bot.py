import os
import sys
import logging
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

# Используем curl_cffi вместо httpx для обхода TLS-fingerprint защиты
from curl_cffi import requests

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


async def check_slots_api(city: str):
    url = CITY_URLS.get(city)
    if not url:
        return None, f"❌ Немає сайту для {city}"

    # Заголовки реального браузера Chrome
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "max-age=0",
        "Upgrade-Insecure-Requests": "1"
    }

    # НАСТРОЙКА ПРОКСИ: Твой рабочий прокси без авторизации
    proxies = {
        "http": "http://162.243.108.161:8080",
        "https": "http://162.243.108.161:8080"
    }

    try:
        # Открываем асинхронную сессию curl_cffi с поддержкой прокси
        async with requests.AsyncSession(proxies=proxies) as session:
            logger.info("Запит через curl_cffi (impersonate='chrome') для міста: %s", city)
            
            # impersonate="chrome" полностью копирует сетевой уровень браузера Google Chrome
            response = await session.get(url, headers=headers, impersonate="chrome", timeout=15.0)
            
            text = response.text.lower()

            if "blocked for security reasons" in text or response.status_code == 403:
                logger.warning("Бот заблокований захистом Cloudflare (403/Blocked)")
                return None, f"🛡️ {city}: Сервер хостингу заблокований захистом сайту. Потрібно підключити або змінити прокси."

            if "наразі всі місця зайняті" in text:
                logger.info("Термінів немає: %s", city)
                return False, f"❌ {city}: термінів немає"

            elif "продовжити" in text or "зареєструватися" in text:
                logger.info("Знайдено вільні терміни: %s", city)
                return True, f"✅ {city}: є вільні терміни!"

            logger.info("Невідомий статус сторінки: %s", city)
            return None, f"⚠️ {city}: сайт доступний, але відповідь нетипова."

    except Exception as e:
        logger.exception("Помилка запиту %s", city)
        return None, f"❌ Помилка з'єднання: {e}"


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
            await update.message.reply_text("⏳ Перевіряю статус через curl_cffi (Chrome Emulation)...")
            _, result = await check_slots_api(city)
            await update.message.reply_text(result)
        case "▶ Увімкнути моніторинг":
            context.chat_data["monitoring"] = True
            await update.message.reply_text("✅ Моніторинг активований")
        case "⛔ Зупинити моніторинг":
            context.chat_data["monitoring"] = False
            await update.message.reply_text("⛔ Моніторинг зупинено")
        case "🛠 Debug":
            city = context.chat_data.get("city", "Мюнхен")
            await update.message.reply_text("🕵️‍♂️ Зчитую сирий HTML сторінки за допомогою curl_cffi...")
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                proxies = {
                    "http": "http://162.243.108.161:8080",
                    "https": "http://162.243.108.161:8080"
                }
                async with requests.AsyncSession(proxies=proxies) as session:
                    resp = await session.get(CITY_URLS[city], headers=headers, impersonate="chrome", timeout=15.0)
                    clean_text = resp.text[:600].replace('\n', ' ')
                    await update.message.reply_text(
                        f"📊 Код відповіді: {resp.status_code}\n"
                        f"📋 Конфіг: {context.chat_data}\n\n"
                        f"📄 Сирий текст:\n{clean_text}..."
                    )
            except Exception as e:
                await update.message.reply_text(f"❌ Помилка дебагу: {e}")
        case _:
            await update.message.reply_text("Невідома команда. Натисніть кнопку.")


# ====================== СИСТЕМНЫЙ МОНИТОРИНГ ======================

async def monitor_job(context: ContextTypes.DEFAULT_TYPE):
    application = context.application
    active_cities = set()

    for chat_id, data in application.chat_data.items():
        if data.get("monitoring", False):
            active_cities.add(data.get("city", "Мюнхен"))

    if not active_cities:
        return

    tasks = {city: check_slots_api(city) for city in active_cities}
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    
    city_states = {}
    for city, res in zip(tasks.keys(), results):
        if isinstance(res, Exception):
            city_states[city] = (None, f"❌ Помилка: {res}")
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
                    logger.error(f"Помилка відправки: {e}")

            if state is not None:
                data["last_state"] = state


def main():
    if not TOKEN:
        sys.exit(1)

    persistence = PicklePersistence(filepath="/app/data/bot_persistence.pickle")

    application = (
        Application.builder()
        .token(TOKEN)
        .persistence(persistence)
        .build()
    )

    job_queue = application.job_queue
    job_queue.run_repeating(monitor_job, interval=60, first=10, name="slots_monitoring_job")

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
