from pydantic import BaseModel, Field
from typing import Annotated, List, Optional, Dict, Any

# Ce schéma est identique à celui du notebook, comme demandé.
class ChatRequest(BaseModel):
    prompt: str
    temperature: str = "0"
    template_prompt: Optional[str] = ""
    chat_model: str = "gpt-4.1-2025-04-14"
 
class LLMOptions(BaseModel):
    chat_model: str = "gpt-4.1-2025-04-14"
    temperature: float = 0.0
    template_prompt: Optional[str] = ""

# Schéma de réponse détaillé pour correspondre à la sortie des fonctions de recherche
class chatResponse(BaseModel):
    response: str
    chat_model: Optional[str] = "gpt-4.1-2025-04-14"
    temperature: float = 0.0
    time_elapsed: Optional[float] = None
    options: Optional[Dict[str, Any]] = None
