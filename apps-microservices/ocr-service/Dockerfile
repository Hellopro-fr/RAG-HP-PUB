FROM vllm/vllm-openai:v0.8.2 AS dev

# Install Python 3.11
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends python3.11 python3.11-venv python3-pip python3.11-dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Ensure Python 3.11 is default
RUN ln -sf /usr/bin/python3.11 /usr/bin/python

ENV GRADIO_SERVER_PORT=8559
ENV GRADIO_SERVER_NAME="0.0.0.0"
EXPOSE 8559

WORKDIR /app

# Create and activate virtual environment
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Install dependencies
COPY requirements.txt setup.py README.md /app/
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Installer docext depuis la source
RUN git clone https://github.com/nanonets/docext.git
WORKDIR /app/docext
RUN apt-get update && apt-get install -y poppler-utils && rm -rf /var/lib/apt/lists/*
RUN pip install -e .

WORKDIR /app

RUN pip install --no-cache-dir flash-attn --no-build-isolation

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
