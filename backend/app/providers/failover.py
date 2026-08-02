"""Small failover adapters used by the deadline-bound live challenge."""

from __future__ import annotations

import asyncio
from typing import Any

from backend.app.providers.interfaces import ChatMessage, ContentExtractionProvider, LLMProvider


class FailoverLLMProvider:
    def __init__(
        self,
        primary: LLMProvider,
        backup: LLMProvider | None = None,
        *,
        timeout_seconds: int = 75,
    ) -> None:
        self.primary = primary
        self.backup = backup
        self.timeout_seconds = timeout_seconds
        self.last_provider = "primary"
        self._events: list[dict[str, str]] = []

    async def complete(self, messages: list[ChatMessage]) -> str:
        return await self._call("complete", messages)

    async def complete_structured(self, messages: list[ChatMessage], response_schema: type[Any]) -> Any:
        failures: list[str] = []
        for index, (label, provider) in enumerate((("primary", self.primary), ("backup", self.backup))):
            if provider is None:
                continue
            attempts = 2 if index == 0 else 1
            current_messages = messages
            for attempt in range(attempts):
                try:
                    value = await asyncio.wait_for(
                        provider.complete_structured(current_messages, response_schema),
                        timeout=self.timeout_seconds,
                    )
                    self.last_provider = label
                    if failures:
                        self._events.append({
                            "capability": "llm",
                            "operation": "complete_structured",
                            "selected_channel": label,
                            "failed_channels": ", ".join(failures),
                        })
                    return value
                except Exception as exc:
                    failures.append(f"{label}:{type(exc).__name__}:attempt{attempt + 1}")
                    if attempt == 0 and attempts == 2:
                        schema = (
                            response_schema.model_json_schema()
                            if isinstance(response_schema, type) and hasattr(response_schema, "model_json_schema")
                            else {"type": "object"}
                        )
                        current_messages = [*messages, ChatMessage(
                            role="user",
                            content=(
                                "上一次输出未通过 Schema 校验。只返回一个严格 JSON 对象；"
                                "字段名、必填字段和类型必须完全符合以下 JSON Schema：\n"
                                + str(schema)
                            ),
                        )]
        raise RuntimeError("all LLM providers failed: " + "; ".join(failures))

    async def _call(self, method: str, *args: Any) -> Any:
        failures: list[str] = []
        for label, provider in (("primary", self.primary), ("backup", self.backup)):
            if provider is None:
                continue
            try:
                value = await asyncio.wait_for(
                    getattr(provider, method)(*args),
                    timeout=self.timeout_seconds,
                )
                self.last_provider = label
                if failures:
                    self._events.append({
                        "capability": "llm",
                        "operation": method,
                        "selected_channel": label,
                        "failed_channels": ", ".join(failures),
                    })
                return value
            except Exception as exc:
                failures.append(f"{label}:{type(exc).__name__}")
        raise RuntimeError("all LLM providers failed: " + "; ".join(failures))

    def drain_failover_events(self) -> list[dict[str, str]]:
        events, self._events = self._events, []
        return events


class FailoverContentExtractionProvider:
    def __init__(
        self,
        primary: ContentExtractionProvider,
        backup: ContentExtractionProvider | None = None,
        *,
        timeout_seconds: int = 25,
    ) -> None:
        self.primary = primary
        self.backup = backup
        self.timeout_seconds = timeout_seconds
        self._events: list[dict[str, str]] = []

    async def extract_url(self, url: str):
        failures: list[str] = []
        for label, provider in (("primary", self.primary), ("backup", self.backup)):
            if provider is None:
                continue
            try:
                page = await asyncio.wait_for(provider.extract_url(url), timeout=self.timeout_seconds)
                if len((page.raw_text or "").strip()) < 120:
                    raise ValueError("extracted body is too short")
                if failures:
                    self._events.append({
                        "capability": "extraction",
                        "operation": "extract_url",
                        "selected_channel": label,
                        "failed_channels": ", ".join(failures),
                    })
                return page
            except Exception as exc:
                failures.append(f"{label}:{type(exc).__name__}")
        raise RuntimeError("all extraction providers failed: " + "; ".join(failures))

    def drain_failover_events(self) -> list[dict[str, str]]:
        events, self._events = self._events, []
        return events
