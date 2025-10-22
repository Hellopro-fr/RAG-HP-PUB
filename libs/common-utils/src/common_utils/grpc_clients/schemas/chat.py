from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    prompt: str
    temperature: float = 0.7
    max_tokens: int = 1024
    enable_thinking: bool = False
    options: Optional[Dict[str, Any]] = {
        "top_p": float(0.8),
        "top_k": int(20),
        "repetition_penalty": float(1.0),
    }
