# Start from a lightweight Python base image
FROM python:3.10.17-slim

# Set the working directory inside the container
WORKDIR /app

# Set the PYTHONPATH to ensure Python can find our script
ENV PYTHONPATH=/app

# Copy the requirements file first to leverage Docker's build cache
COPY tools/requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the scripts into the container
COPY tools/dlq_archiver.py .
COPY tools/dlq_requeuer.py .
COPY tools/es_mapping.py .
COPY tools/connections.py .

# Run as non-root user
RUN useradd -r -u 1001 appuser && chown -R appuser /app
USER appuser

# Healthcheck: verify the archiver process is still running
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD pgrep -f dlq_archiver.py || exit 1

# Define the command that will be run when the container starts
# Override with docker-compose CMD to run dlq_requeuer.py instead
CMD ["python", "-u", "dlq_archiver.py"]
