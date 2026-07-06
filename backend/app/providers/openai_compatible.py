"""OpenAI-compatible structured LLM provider."""

import json
import re
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
        timeout_seconds: int = 300,
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
        }
        # Only request JSON mode when the caller expects structured data
        if response_schema is not str:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            try:
                data = response.json()
            except json.JSONDecodeError as exc:
                preview = response.text[:800].replace("\n", "\\n")
                raise ValueError(
                    f"LLM endpoint returned non-JSON HTTP body "
                    f"(status={response.status_code}): {preview}"
                ) from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            preview = json.dumps(data, ensure_ascii=False)[:800]
            raise ValueError(f"LLM response missing choices/message/content: {preview}") from exc

        # If caller expects plain text, return as-is
        if response_schema is str:
            return content

        # Try parsing as JSON; fall back to raw text if the API ignored json_object mode
        try:
            parsed = _loads_llm_json(content)
        except json.JSONDecodeError as exc:
            if response_schema is dict:
                return {"text": content}
            preview = content[:800].replace("\n", "\\n")
            raise ValueError(f"LLM returned non-JSON structured content: {preview}") from exc

        if response_schema is dict:
            return parsed
        if isinstance(response_schema, type) and issubclass(response_schema, BaseModel):
            return response_schema.model_validate(parsed)
        return parsed


def _loads_llm_json(content: str) -> Any:
    """Parse JSON even when a model wraps it in markdown fences or prose."""

    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start_candidates = [idx for idx in (text.find("{"), text.find("[")) if idx >= 0]
        if not start_candidates:
            raise
        start = min(start_candidates)
        end = max(text.rfind("}"), text.rfind("]"))
        if end <= start:
            raise
        return json.loads(text[start:end + 1])
