# --- Étape 0: Base ---
FROM vllm/vllm-openai:v0.8.2 AS dev

# Install Python 3.11
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends python3.11 python3.11-venv python3-pip python3.11-dev git && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Ensure Python 3.11 is default
RUN ln -sf /usr/bin/python3.11 /usr/bin/python

WORKDIR /app

# --- Étape 1: Définir le PYTHONPATH ---
ENV PYTHONPATH=/app
ENV CUDA_HOME=/usr/local/cuda/bin/nvcc
ENV PATH=$CUDA_HOME/bin:$PATH
ENV LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH

# Copier les requirements du service
COPY apps-microservices/ocr-service/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Installer docext depuis la source
RUN git clone https://github.com/nanonets/docext.git
WORKDIR /app/docext
RUN apt-get update && apt-get install -y poppler-utils && rm -rf /var/lib/apt/lists/*
RUN pip install -e .

WORKDIR /app

RUN pip install --no-cache-dir flash-attn --no-build-isolation

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
