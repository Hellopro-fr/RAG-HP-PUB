# Use the official llama-cpp-python image as a base
FROM ghcr.io/abetlen/llama-cpp-python:latest

# Switch to root user to install packages
USER root

# Install wget and other necessary tools
RUN apt-get update && apt-get install -y --no-install-recommends wget && \
    rm -rf /var/lib/apt/lists/*

# Create a directory to store the models
RUN mkdir -p /models && chown -R app:app /models

# Switch back to the non-root user
USER app

# Copy the entrypoint script into the container
COPY scripts/entrypoint-llamacpp.sh /usr/local/bin/entrypoint-llamacpp.sh

# Make the script executable
RUN chmod +x /usr/local/bin/entrypoint-llamacpp.sh

# Set the entrypoint for the container
ENTRYPOINT ["/usr/local/bin/entrypoint-llamacpp.sh"]
