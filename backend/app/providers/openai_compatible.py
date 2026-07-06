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
        max_tokens: int = 4096,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens

    async def complete(
        self,
        messages: list[ChatMessage],
    ) -> str:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = _loads_response_json(response)

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            preview = json.dumps(data, ensure_ascii=False)[:800]
            raise ValueError(f"LLM response missing choices/message/content: {preview}") from exc

    async def complete_structured(
        self,
        messages: list[ChatMessage],
        response_schema: type[Any],
    ) -> Any:
        if response_schema is str:
            return await self.complete(messages)

        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
        }
        payload["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = _loads_response_json(response)

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            preview = json.dumps(data, ensure_ascii=False)[:800]
            raise ValueError(f"LLM response missing choices/message/content: {preview}") from exc

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
        balanced = _balanced_json_prefix(text[start:])
        if balanced:
            return json.loads(balanced)
        end = max(text.rfind("}"), text.rfind("]"))
        if end <= start:
            raise
        return json.loads(text[start:end + 1])


def _loads_response_json(response: httpx.Response) -> Any:
    """Parse normal OpenAI JSON and SSE/keepalive-wrapped JSON bodies."""

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        text = response.text.strip()
        parsed = _loads_sse_wrapped_json(text)
        if parsed is not None:
            return parsed
        preview = response.text[:800].replace("\n", "\\n")
        raise ValueError(
            f"LLM endpoint returned non-JSON HTTP body "
            f"(status={response.status_code}): {preview}"
        ) from exc


def _loads_sse_wrapped_json(text: str) -> Any | None:
    """Some OpenAI-compatible gateways prepend keepalive/SSE lines to JSON."""

    if not text:
        return None
    candidates: list[str] = []
    data_lines: list[str] = []
    passthrough_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(":") or stripped.startswith("event:"):
            continue
        if stripped.startswith("data:"):
            payload = stripped.removeprefix("data:").strip()
            if payload and payload != "[DONE]":
                data_lines.append(payload)
            continue
        passthrough_lines.append(stripped)
    if data_lines:
        candidates.append("\n".join(data_lines))
    if passthrough_lines:
        candidates.append("\n".join(passthrough_lines))
    candidates.append(text)
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            start_candidates = [idx for idx in (candidate.find("{"), candidate.find("[")) if idx >= 0]
            if not start_candidates:
                continue
            start = min(start_candidates)
            balanced = _balanced_json_prefix(candidate[start:])
            if balanced:
                try:
                    return json.loads(balanced)
                except json.JSONDecodeError:
                    continue
    return None


def _balanced_json_prefix(text: str) -> str | None:
    """Return the first balanced JSON object/array substring, respecting strings."""

    if not text or text[0] not in "{[":
        return None
    stack = [text[0]]
    in_string = False
    escaped = False
    for index, char in enumerate(text[1:], start=1):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in "{[":
            stack.append(char)
            continue
        if char in "}]":
            if not stack:
                return None
            opener = stack.pop()
            if (opener, char) not in {("{", "}"), ("[", "]")}:
                return None
            if not stack:
                return text[: index + 1]
    return None
