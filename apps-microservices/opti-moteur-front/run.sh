#!/bin/bash
# Run uvicorn en mode dev (reload).
# Prerequis : source .venv/bin/activate && pip install -r requirements.txt

set -e

if [ -d .venv ]; then
    source .venv/bin/activate
fi

uvicorn main:app --host 0.0.0.0 --port 8570 --reload
