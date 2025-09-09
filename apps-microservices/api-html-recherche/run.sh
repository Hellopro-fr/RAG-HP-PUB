#!/bin/bash
echo "Activation de l'environnement virtuel..."
source .venv/bin/activate

uvicorn main:app --host 0.0.0.0 --port 8550 --reload
