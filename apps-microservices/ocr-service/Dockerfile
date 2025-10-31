FROM vllm/vllm-openai:v0.8.2 AS dev

# Install Python 3.11
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    poppler-utils \
    git && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Ensure Python 3.11 is default
RUN ln -sf /usr/bin/python3.11 /usr/bin/python

ENV GRADIO_SERVER_PORT=8559
ENV GRADIO_SERVER_NAME="0.0.0.0"
EXPOSE 8559

WORKDIR /app

# Create venv without system-site-packages
RUN python3.11 -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Install dependencies
COPY apps-microservices/ocr-service/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Installer docext depuis la source
RUN git clone https://github.com/nanonets/docext.git
WORKDIR /app/docext
RUN apt-get update && apt-get install -y poppler-utils && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -e .

WORKDIR /app/

RUN awk '/uvloop.run\(run_server\(args\)\)/ { \
    print "    # --- Patch CUDA Graph ---"; \
    print "    if hasattr(args, '\''enforce_eager'\''):"; \
    print "        args.enforce_eager = False"; \
}1' /app/.venv/lib/python3.11/site-packages/vllm/entrypoints/openai/api_server.py \
> /tmp/api_server.py \
&& mv /tmp/api_server.py /app/.venv/lib/python3.11/site-packages/vllm/entrypoints/openai/api_server.py


# Installer flash-attn AVANT ou vérifier la version de PyTorch
RUN pip install --no-cache-dir ninja packaging && \
    pip install flash-attn==2.5.9.post1 flashinfer-python --no-build-isolation

ENTRYPOINT ["/app/.venv/bin/python", "-m", "docext.app.app", "--no-share","--model_name", "hosted_vllm/nanonets/Nanonets-OCR-s", "--server_port", "8559","--concurrency_limit", "15","--vlm_server_port", "8181"]

