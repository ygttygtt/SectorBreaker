import asyncio

from backend.app.providers.interfaces import ChatMessage
from backend.app.providers.openai_compatible import OpenAICompatibleLLMProvider


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"sections":["行业边界","玩家结构"],"key_questions":["谁付钱？"]}'
                    }
                }
            ]
        }


class FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        self.requests: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def post(self, url: str, json: dict, headers: dict) -> FakeResponse:
        self.requests.append({"url": url, "json": json, "headers": headers})
        return FakeResponse()


def test_openai_compatible_provider_returns_json(monkeypatch) -> None:
    import backend.app.providers.openai_compatible as provider_module

    monkeypatch.setattr(provider_module.httpx, "AsyncClient", FakeAsyncClient)
    provider = OpenAICompatibleLLMProvider(
        base_url="https://llm.example.com/v1",
        api_key="test-key",
        model="test-model",
    )

    result = asyncio.run(
        provider.complete_structured(
            messages=[ChatMessage(role="user", content="plan")],
            response_schema=dict,
        )
    )

    assert result["sections"] == ["行业边界", "玩家结构"]
    assert result["key_questions"] == ["谁付钱？"]


def test_openai_compatible_provider_parses_keepalive_wrapped_body(monkeypatch) -> None:
    import backend.app.providers.openai_compatible as provider_module

    class KeepaliveResponse:
        status_code = 200
        text = (
            ': keepalive\n\n'
            '{"choices":[{"message":{"content":"# 标题\\n\\n## 小节\\n\\n正文"}}]}'
        )

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            raise provider_module.json.JSONDecodeError("wrapped", self.text, 0)

    class KeepaliveClient(FakeAsyncClient):
        async def post(self, url: str, json: dict, headers: dict) -> KeepaliveResponse:
            self.requests.append({"url": url, "json": json, "headers": headers})
            return KeepaliveResponse()

    monkeypatch.setattr(provider_module.httpx, "AsyncClient", KeepaliveClient)
    provider = OpenAICompatibleLLMProvider(
        base_url="https://llm.example.com/v1",
        api_key="test-key",
        model="test-model",
    )

    result = asyncio.run(provider.complete([ChatMessage(role="user", content="write")]))

    assert result.startswith("# 标题")
