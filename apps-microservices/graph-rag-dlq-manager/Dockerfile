# apps-microservices/graph-rag-dlq-manager/Dockerfile

FROM python:3.10-slim
# refresh OS packages of the final stage (fixable CVEs in base layers)
RUN apt-get update && apt-get -y upgrade && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# Set PYTHONPATH for imports
ENV PYTHONPATH=/app

# Install shared library
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Install service requirements
COPY apps-microservices/graph-rag-dlq-manager/requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY apps-microservices/graph-rag-dlq-manager .

# Expose port
EXPOSE 8520

# Run with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8520"]
