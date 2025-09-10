#!/bin/bash

echo "Création de l'environnement virtuel..."
python3 -m venv .venv

echo "Activation de l'environnement virtuel..."
source .venv/bin/activate

echo "Installation de dépendences..."
pip install -r requirements.txt