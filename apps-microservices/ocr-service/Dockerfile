# --- Étape 0: Base ---
FROM python:3.11-slim
WORKDIR /app

# --- Étape 1: Définir le PYTHONPATH ---
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y git \
    && rm -rf /var/lib/apt/lists/*

# Copier les requirements du service
COPY apps-microservices/ocr-service/requirements.txt .
RUN pip install -r requirements.txt

# Installer docext depuis la source
RUN git clone https://github.com/nanonets/docext.git
WORKDIR /app/docext
RUN apt-get update && apt-get install -y poppler-utils && rm -rf /var/lib/apt/lists/*
RUN pip install -e .

WORKDIR /app

EXPOSE 8559

CMD [ \
  "python", \
  "-m", "docext.app.app",\
  "--model_name", "hosted_vllm/nanonets/Nanonets-OCR-s", \
  "--gpu_memory_utilization", "0.95",\
  "--concurrency_limit", "15",\
  "--dtype", "float16",\
  "--server_port", "8559",\
  "--vlm_server_port", "8181"\
]
