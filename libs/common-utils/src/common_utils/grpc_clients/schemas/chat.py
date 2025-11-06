from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from enum import Enum

class ChatProvider(str, Enum):
    DEEPSEEK = "deepseek"
    GPT = "gpt"
    OPENROUTER = "openrouter"

class ChatRequest(BaseModel):
    prompt: str
    model: str = "deepseek-chat"
    provider: ChatProvider = ChatProvider.DEEPSEEK
    temperature: float = 0.7
    max_tokens: int = 1024
    enable_thinking: bool = False
    options: Optional[Dict[str, Any]] = {
        "top_p": float(0.8),
        "top_k": int(20),
        # "repetition_penalty": float(1.0),
    }
