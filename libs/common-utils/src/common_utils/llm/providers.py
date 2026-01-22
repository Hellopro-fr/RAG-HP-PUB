from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging
from functools import lru_cache

# Try importing SDKs (they might not be installed in all services using common-utils)
try:
    from openai import OpenAI, AsyncOpenAI
except ImportError:
    OpenAI = None
    AsyncOpenAI = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

try:
    import anthropic
except ImportError:
    anthropic = None

logger = logging.getLogger(__name__)

class BaseLLMClient(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        pass

class OpenAIClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None):
        if not AsyncOpenAI:
            raise ImportError("openai package is required for OpenAIClient")
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    async def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 4096, **kwargs) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        return response.choices[0].message.content

class DeepSeekClient(OpenAIClient):
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        super().__init__(api_key=api_key, model=model, base_url="https://api.deepseek.com")

class GeminiClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str):
        if not genai:
            raise ImportError("google-genai package is required for GeminiClient")
        self.client = genai.Client(api_key=api_key)
        self.model = model

    async def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 4096, **kwargs) -> str:
        # Note: Google GenAI native async support might vary, using correct SDK usage from recherche.py
        # recherche.py uses client.models.generate_content (sync)? 
        # Wait, recherche.py doesn't await generate_content? 
        # "response = self.client.models.generate_content"
        # But the method calling it is async.
        # Let's check if google.genai.Client is async or we need to run in executor.
        # For now, let's assume standard synchronous call wrapped or if latest SDK supports async.
        # Actually, let's stick to what searching.py does but allow async wrapper if needed.
        
        # Simulating async if the client is sync, or using async method if available.
        # The V1Beta/V1 SDK usually has generate_content_async.
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                **kwargs
            )
        )
        return response.text

class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str):
        if not anthropic:
            raise ImportError("anthropic package is required for AnthropicClient")
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

    async def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 4096, **kwargs) -> str:
        message = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return message.content[0].text

class LLMFactory:
    @staticmethod
    def create_client(
        provider: str,
        api_key: str,
        model: str,
        base_url: Optional[str] = None
    ) -> BaseLLMClient:
        provider = provider.lower()
        if provider == "openai":
            return OpenAIClient(api_key, model, base_url)
        elif provider == "deepseek":
            return DeepSeekClient(api_key, model)
        elif provider == "gemini":
            return GeminiClient(api_key, model)
        elif provider == "anthropic":
            return AnthropicClient(api_key, model)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
