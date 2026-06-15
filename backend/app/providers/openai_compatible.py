"""OpenAI-compatible structured LLM provider."""

import json
from typing import Any

import httpx
from pydantic import BaseModel

from backend.app.providers.interfaces import ChatMessage


class OpenAICompatibleLLMProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.2,
        timeout_seconds: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds

    async def complete_structured(
        self,
        messages: list[ChatMessage],
        response_schema: type[Any],
    ) -> Any:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if response_schema is dict:
            return parsed
        if isinstance(response_schema, type) and issubclass(response_schema, BaseModel):
            return response_schema.model_validate(parsed)
        return parsed
