from pydantic import BaseModel
from typing import Dict, Any

# Ce schéma est identique à celui du notebook, comme demandé.
class ClassificationRequest(BaseModel):
    data: Dict[str, Any]

# Schéma de réponse détaillé pour correspondre à la sortie des fonctions de recherche
class ClassificationResponse(BaseModel):
    response: Dict[str, Any]