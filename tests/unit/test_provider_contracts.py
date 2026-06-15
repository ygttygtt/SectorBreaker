import asyncio

from backend.app.providers.fakes import FakeLLMProvider, FakeRetrievalProvider, FakeSearchProvider
from backend.app.providers.interfaces import ChatMessage, SearchQuery


def test_fake_llm_returns_structured_response() -> None:
    provider = FakeLLMProvider(response={"answer": "ok", "evidence_ids": ["EV-001"]})

    result = asyncio.run(
        provider.complete_structured(
            messages=[ChatMessage(role="user", content="summarize")],
            response_schema=dict,
        )
    )

    assert result == {"answer": "ok", "evidence_ids": ["EV-001"]}


def test_fake_search_provider_records_query_and_returns_results() -> None:
    provider = FakeSearchProvider(
        results=[
            {
                "title": "AI agent market",
                "url": "https://example.com/ai-agent-market",
                "snippet": "A useful source.",
            }
        ]
    )

    results = asyncio.run(
        provider.search(SearchQuery(query="AI agent market", market_scope="mixed", max_results=3))
    )

    assert provider.queries == ["AI agent market"]
    assert results[0].url == "https://example.com/ai-agent-market"


def test_fake_retrieval_provider_indexes_and_searches_project_text() -> None:
    provider = FakeRetrievalProvider()
    provider.index_text(project_id="project-1", document_id="doc-1", text="AI agents automate research")

    results = provider.search_project(project_id="project-1", query="research", limit=5)

    assert [item.document_id for item in results] == ["doc-1"]
