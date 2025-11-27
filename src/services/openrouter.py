"""OpenRouter API client for Grok integration."""

import logging
from dataclasses import dataclass
from typing import List, Optional

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """Chat message structure for OpenRouter API."""
    role: str  # 'system', 'user', or 'assistant'
    content: str


@dataclass
class ChatResponse:
    """Response from OpenRouter API."""
    content: str
    model: str
    tokens_prompt: int
    tokens_completion: int
    finish_reason: str


class OpenRouterError(Exception):
    """Exception for OpenRouter API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class OpenRouterClient:
    """Async client for OpenRouter API."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.openrouter_base_url
        self.api_key = self.settings.openrouter_api_key
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/DentalResearchBot",
                    "X-Title": "DentalResearchBot",
                },
                timeout=120.0,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def chat_completion(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> ChatResponse:
        """Send chat completion request to OpenRouter."""
        if model is None:
            model = self.settings.openrouter_default_model

        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            response = await self.client.post("/chat/completions", json=payload)

            if response.status_code == 429:
                raise OpenRouterError("Rate limit exceeded. Please try again later.", 429)

            if response.status_code != 200:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", {}).get("message", response.text)
                raise OpenRouterError(f"API error: {error_msg}", response.status_code)

            data = response.json()

            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            usage = data.get("usage", {})

            return ChatResponse(
                content=message.get("content", ""),
                model=data.get("model", model),
                tokens_prompt=usage.get("prompt_tokens", 0),
                tokens_completion=usage.get("completion_tokens", 0),
                finish_reason=choice.get("finish_reason", "stop"),
            )

        except httpx.TimeoutException:
            raise OpenRouterError("Request timed out. Please try again.", None)
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            raise OpenRouterError(f"Connection error: {str(e)}", None)


# Global client instance
_client: Optional[OpenRouterClient] = None


def get_openrouter_client() -> OpenRouterClient:
    """Get or create OpenRouter client instance."""
    global _client
    if _client is None:
        _client = OpenRouterClient()
    return _client


async def close_openrouter_client() -> None:
    """Close OpenRouter client."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None

