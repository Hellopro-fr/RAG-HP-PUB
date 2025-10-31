# DeepSeek-OCR vLLM Docker Image
# Based on official vLLM OpenAI image for better compatibility

FROM vllm/vllm-openai:v0.8.5

# Switch to root user to install packages
USER root

# Set working directory
WORKDIR /app

# Copy the DeepSeek-OCR vLLM implementation
COPY ./apps-microservices/DeepSeek-OCR/DeepSeek-OCR-master/DeepSeek-OCR-vllm/ ./DeepSeek-OCR-vllm/

# Copy custom files to replace the originals (transparent replacement approach)
COPY ./apps-microservices/DeepSeek-OCR/custom_config.py ./DeepSeek-OCR-vllm/config.py
COPY ./apps-microservices/DeepSeek-OCR/custom_image_process.py ./DeepSeek-OCR-vllm/process/image_process.py
COPY ./apps-microservices/DeepSeek-OCR/custom_deepseek_ocr.py ./DeepSeek-OCR-vllm/deepseek_ocr.py

# Copy custom run scripts to replace the originals
COPY ./apps-microservices/DeepSeek-OCR/custom_run_dpsk_ocr_pdf.py ./DeepSeek-OCR-vllm/run_dpsk_ocr_pdf.py
COPY ./apps-microservices/DeepSeek-OCR/custom_run_dpsk_ocr_image.py ./DeepSeek-OCR-vllm/run_dpsk_ocr_image.py
COPY ./apps-microservices/DeepSeek-OCR/custom_run_dpsk_ocr_eval_batch.py ./DeepSeek-OCR-vllm/run_dpsk_ocr_eval_batch.py

# Copy the startup script
COPY ./apps-microservices/DeepSeek-OCR/start_server.py .

# Copy requirements file and install additional dependencies
COPY ./apps-microservices/DeepSeek-OCR/requirements.txt .

# Install Python dependencies excluding conflicting packages
RUN pip install --no-cache-dir \
    PyMuPDF \
    img2pdf \
    einops \
    easydict \
    addict \
    Pillow \
    numpy

# Install additional dependencies for the API server
RUN pip install --no-cache-dir \
    fastapi==0.104.1 \
    uvicorn[standard]==0.24.0 \
    python-multipart==0.0.6

# Install flash-attn for optimal performance (if not already included)
RUN pip install --no-cache-dir flash-attn==2.7.3 --no-build-isolation || echo "flash-attn may already be installed"

# Downgrade tokenizers to compatible version if needed
RUN pip install --no-cache-dir tokenizers==0.13.3 || echo "Using existing tokenizers version"

# Add the DeepSeek-OCR directory to PYTHONPATH
ENV PYTHONPATH="/app/DeepSeek-OCR-vllm:${PYTHONPATH}"

# Create directories for outputs
RUN mkdir -p /app/outputs
RUN mkdir -p /app/models

# Make the scripts executable
RUN chmod +x /app/start_server.py

# Expose the API port
EXPOSE 8501

# Set the default command to use our custom server
# Override the entrypoint to run our script directly
# Use the full path to python to avoid PATH issues
ENTRYPOINT ["/usr/bin/python3", "/app/start_server.py"]