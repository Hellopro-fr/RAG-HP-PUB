FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only for POC)
RUN playwright install --with-deps chromium

# Copy application code
COPY src/ ./src/
COPY app/ ./app/

# Set python path
ENV PYTHONPATH=/app

# Expose API port
# Expose API port (Classic Crawler Service Port)
EXPOSE 8503

# Start FastAPI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8503"]
