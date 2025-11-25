from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from enum import Enum


class ChatBaseURL(str, Enum):
    DEEPSEEK = "https://api.deepseek.com"
    OPENAI = "https://api.openai.com/v1"
    OPENROUTER = "https://openrouter.ai/api/v1"


class ChatProvider(str, Enum):
    DEEPSEEK = "deepseek"
    GPT = "gpt"
    OPENROUTER = "openrouter"


class ChatRequest(BaseModel):
    prompt: str
    model: str = ""
    # provider: ChatProvider = ChatProvider.DEEPSEEK
    provider: str = ChatProvider.DEEPSEEK
    temperature: float = 0.7
    max_tokens: int = 1024
    enable_thinking: bool = False
    thinking_level: Optional[str] = None
    options: Optional[Dict[str, Any]] = {
        "top_p": float(0.8),
        "top_k": int(20),
        # "repetition_penalty": float(1.0),
    }
    max_retries: int = 6
