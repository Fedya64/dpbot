FROM python:3.12-slim

# Важливо: додаємо tzdata
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    wget curl unzip \
    libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libpangocairo-1.0-0 \
    libasound2 libx11-xcb1 fonts-unifont \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium --only-shell

COPY bot.py .

CMD ["python", "bot.py"]
