#!/bin/bash
set -e

# --- Configuration ---
# The target directory inside the container where models are stored.
MODEL_DIR="/models"
# The expected filename for the model. The script will rename the downloaded file to this.
MODEL_FILENAME="model.gguf"
# The full path to the model file.
MODEL_PATH="${MODEL_DIR}/${MODEL_FILENAME}"

# --- Model Download Logic ---

# Check if the GGUF_MODEL_URL environment variable is set.
if [ -z "${GGUF_MODEL_URL}" ]; then
    echo "ERROR: GGUF_MODEL_URL environment variable is not set."
    echo "Please set it to the direct download URL of the GGUF model you want to use."
    exit 1
fi

# Check if the model file already exists.
if [ -f "${MODEL_PATH}" ]; then
    echo "INFO: Model file already exists at ${MODEL_PATH}. Skipping download."
else
    echo "INFO: Model file not found. Starting download from ${GGUF_MODEL_URL}..."
    # Download the model using wget. The -O flag specifies the output file path.
    # The --progress=bar:force ensures the progress bar is shown even in a script.
    wget -O "${MODEL_PATH}" --progress=bar:force "${GGUF_MODEL_URL}"
    echo "INFO: Download complete."
fi

# --- Server Startup Logic ---

# All arguments passed to this script (like --host, --port from the Docker command) are captured in "$@".
# We will append our required arguments to this list.

echo "INFO: Starting llama.cpp server..."

# Execute the llama.cpp server, passing along all arguments provided to this script.
# This makes the script flexible and allows passing arguments from the docker-compose file.
exec python -m llama_cpp.server --model "${MODEL_PATH}" "$@"
