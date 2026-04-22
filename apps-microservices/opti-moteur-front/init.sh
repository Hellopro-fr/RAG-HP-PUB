#!/bin/bash
# Initialisation : venv + install des dependances.

set -e

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "=== OK ==="
echo "Pour lancer :"
echo "  ./run.sh"
echo "Ou en prod :"
echo "  docker compose up -d"
