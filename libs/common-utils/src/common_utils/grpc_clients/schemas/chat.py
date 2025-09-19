from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    prompt: str
    temperature: float = 0.7
    max_tokens: int = 1024
    enable_thinking: bool = False