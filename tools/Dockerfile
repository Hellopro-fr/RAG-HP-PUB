# Start from a lightweight Python base image
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app

# Set the PYTHONPATH to ensure Python can find our script
ENV PYTHONPATH=/app

# Copy the requirements file first to leverage Docker's build cache
COPY tools/requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the archiver script into the container
COPY tools/dlq_archiver.py .
COPY tools/dlq_requeuer.py .
COPY tools/es_mapping.py .

# Define the command that will be run when the container starts
CMD ["python", "-u", "dlq_archiver.py"]