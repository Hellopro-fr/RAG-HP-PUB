import sys
import os

# Ajoute le répertoire racine du projet au chemin de Python
# pour que les imports comme "from app.core..." fonctionnent dans les tests.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))