FROM python:3.13-slim

# Install system dependencies untuk Playwright (Firefox)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    fonts-liberation \
    xvfb \
    xauth \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install firefox
RUN playwright install-deps firefox

# Copy application code
COPY . .

# Create debug directory
RUN mkdir -p debug

EXPOSE 8001

# PYTHONUNBUFFERED=1 agar log langsung muncul di docker logs
ENV PYTHONUNBUFFERED=1

# Jalankan langsung — headless mode tidak butuh xvfb
# Jika ingin non-headless (butuh display), set HEADLESS=false di .env
# lalu ganti CMD ke: xvfb-run --auto-servernum python app.py
CMD ["python", "app.py"]
