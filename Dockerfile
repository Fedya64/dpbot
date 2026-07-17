FROM ubuntu:22.04

# Установим системные зависимости для Chromium
RUN apt-get update && apt-get install -y \
    wget curl unzip \
    libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libpangocairo-1.0-0 \
    libasound2 libx11-xcb1 \
    python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Установим Python-зависимости
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Скачаем Chromium для Playwright
RUN python3 -m playwright install chromium

# Скопируем код
COPY . .

# Запуск бота
CMD ["python3", "bot.py"]
