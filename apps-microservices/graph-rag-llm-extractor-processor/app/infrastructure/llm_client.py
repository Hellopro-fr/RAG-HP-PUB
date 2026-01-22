import logging
from typing import Optional

from app.config import settings
from common_utils.llm import LLMFactory

class LLMClient:
    """
    Client for LLM API calls using the centralized common-utils library.
    Acts as a wrapper to maintain interface compatibility with the processor.
    """

    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()
        self.client = self._initialize_client()

    def _initialize_client(self):
        api_key = ""
        model = ""
        
        if self.provider == "openai":
            api_key = settings.OPENAI_API_KEY
            model = settings.OPENAI_MODEL
        elif self.provider == "gemini":
            api_key = settings.GEMINI_API_KEY
            model = settings.GEMINI_MODEL
        elif self.provider == "anthropic":
            api_key = settings.ANTHROPIC_API_KEY
            model = settings.ANTHROPIC_MODEL
        elif self.provider == "deepseek":
            api_key = settings.DEEPSEEK_API_KEY
            model = settings.DEEPSEEK_MODEL

        try:
            print(f"Provider: {self.provider}")
            print(f"API Key: {api_key}")
            print(f"Model: {model}")
            return LLMFactory.create_client(
                provider=self.provider,
                api_key=api_key,
                model=model
            )
        except ImportError as e:
            logging.error(f"Failed to initialize LLM client for {self.provider}: {e}")
            return None
        except Exception as e:
            logging.error(f"Error creating LLM client: {e}")
            return None

    async def generate(self, prompt: str, text: str) -> Optional[str]:
        """
        Generate a completion from the LLM.

        Args:
            prompt: The system/instruction prompt template
            text: The text to analyze

        Returns:
            The LLM response text, or None on error
        """
        if not self.client:
            logging.error("LLM client is not initialized")
            return None

        full_prompt = prompt.format(
            input=text, source_placeholder="{source_placeholder}"
        )

        try:
            return await self.client.generate(
                prompt=full_prompt,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS
            )
        except Exception as e:
            logging.error(f"LLM call failed: {e}")
            return None

# Singleton instance
llm_client = LLMClient()
