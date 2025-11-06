from pydantic import BaseModel, Field
from typing import Annotated, List, Optional, Dict,  Literal, Any

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
    api_response: Dict[str, Any] = {}
    chat_model: Optional[str] = "gpt-4.1-2025-04-14"
    temperature: float = 0.0
    time_elapsed: Optional[float] = None
    options: Optional[Dict[str, Any]] = None

class BatchRequestInput(BaseModel):
    id_request: str = Field(..., description="ID unique de la requête")
    prompt: str = Field(..., description="Prompt chat completion")

class BatchChatRequest(BaseModel):
    list_request: List[BatchRequestInput] = Field(..., description="Liste de requête chat completion")
    enable_thinking: bool = False
    temperature: float = 0.7
    max_tokens: int = 1024   

class BatchResult(BaseModel):    
    id_request: str = Field(..., description="ID unique de la requête")
    llm_response: Optional[Dict[str, Any]] = Field(None, description="Réponse brute de DeepSeek (si applicable)")
    time_elapsed: Optional[float] = None

class BatchRequestResponse(BaseModel):
    resultats: List[BatchResult] = Field(..., description="Résultats de chaque requête batch")
    processing_time_total: float = Field(..., description="Temps total de traitement")