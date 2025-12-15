FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only for POC to save space)
RUN playwright install --with-deps chromium

# Copy source code
COPY src/ ./src/

# Set python path
ENV PYTHONPATH=/app

CMD ["python", "src/main.py"]
