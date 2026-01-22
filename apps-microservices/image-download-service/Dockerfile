FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if any (e.g. for potential future image libraries)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy common utils if needed, though usually we mount/install them. 
# Assuming standard microservice pattern where we copy everything.
COPY . .

# Environment variables
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8505

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8505"]
