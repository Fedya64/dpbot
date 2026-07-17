FROM python:3.12-slim

# Устанавливаем только часовой пояс, остальное для httpx не требуется
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# Создаем папку для персистентного хранения данных бота
RUN mkdir -p /app/data

# Копируем и устанавливаем только чистые Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY bot.py .

CMD ["python", "bot.py"]
