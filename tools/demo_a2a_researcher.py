"""Run the real A2A 1.x Ecosystem Researcher used by the live demo.

Usage:
    python tools/demo_a2a_researcher.py
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Value
from pydantic import BaseModel

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import add_a2a_routes_to_fastapi, create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Part
from a2a.helpers import new_task_from_user_message

from backend.app.agent_network.runtime import ResearchDecision, ResearchSynthesis
from backend.app.config_store import get_runtime_config_path, load_runtime_config
from backend.app.env import load_local_env
from backend.app.providers.factory import (
    build_content_extraction_provider,
    build_content_extraction_provider_from_config,
    build_llm_provider,
    build_llm_provider_from_config,
    build_search_provider,
    build_search_provider_from_config,
)
from backend.app.providers.interfaces import ChatMessage, SearchQuery
from backend.app.providers.failover import FailoverLLMProvider
from backend.app.providers.search_execution import execute_search
from backend.app.providers.source_packs import reliable_domains_for_market
from backend.app.schemas import AgentDeliverable, DeliverableUsage, EvidenceCandidate, WorkOrder


class RemoteInput(BaseModel):
    contract: str
    domain: str
    work_order: WorkOrder


class EcosystemResearcherExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            if context.message is None:
                raise ValueError("A2A request has no message")
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()
        try:
            payload = _request_payload(context)
            deliverable = await _run_real_research(payload)
            value = Value()
            ParseDict({
                "contract": "sectorbreaker.agent-deliverable.v1",
                "deliverable": deliverable.model_dump(mode="json"),
            }, value)
            await updater.add_artifact(
                parts=[Part(data=value, media_type="application/json")],
                name="SectorBreaker AgentDeliverable",
                last_chunk=True,
            )
            await updater.complete()
        except Exception:
            await updater.failed()
            raise

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            raise ValueError("A2A cancel requires an existing task")
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.cancel()


def _request_payload(context: RequestContext) -> RemoteInput:
    if context.message is None:
        raise ValueError("A2A request has no message")
    for part in context.message.parts:
        if part.HasField("data"):
            payload = MessageToDict(part.data, preserving_proto_field_name=True)
            return RemoteInput.model_validate(payload)
        if part.text:
            return RemoteInput.model_validate_json(part.text)
    raise ValueError("A2A request has no structured WorkOrder part")


async def _run_real_research(payload: RemoteInput) -> AgentDeliverable:
    llm, search, extraction = _build_worker_providers()
    llm = FailoverLLMProvider(llm, None) if llm is not None else None
    if llm is None or search is None:
        raise RuntimeError("remote worker requires configured real LLM and SearchProvider")
    work_order = payload.work_order
    decision = await llm.complete_structured(
        [ChatMessage(role="user", content=f"""
你是独立 A2A Ecosystem Researcher。为真实任务生成 1-3 条自然搜索 query。
领域：{payload.domain}
任务：{work_order.objective}
研究角度：{work_order.research_angle}
返回 ResearchDecision JSON。
""".strip())],
        ResearchDecision,
    )
    queries = list(dict.fromkeys([decision.query, *decision.queries]))[:3]
    candidates: list[EvidenceCandidate] = []
    seen_urls: set[str] = set()
    provider_requests = 0
    for query in queries:
        response = await execute_search(
            search,
            SearchQuery(
                query=query,
                market_scope="mixed",
                max_results=4,
                allowed_domains=reliable_domains_for_market("mixed"),
            ),
            request_budget=max(1, work_order.budget.max_provider_requests - provider_requests),
        )
        provider_requests += response.request_count
        for result in response.results:
            if not result.url or result.url in seen_urls:
                continue
            seen_urls.add(result.url)
            candidates.append(EvidenceCandidate(
                candidate_id=f"REMOTE-EV-{len(candidates) + 1}",
                title=result.title or result.url,
                url=result.url,
                snippet=result.snippet,
                provider_metadata=result.provider_metadata or {},
            ))
            if len(candidates) >= 5:
                break
        if len(candidates) >= 5 or provider_requests >= work_order.budget.max_provider_requests:
            break
    if not candidates:
        raise RuntimeError("remote search returned no candidate URLs")

    async def extract(candidate: EvidenceCandidate) -> EvidenceCandidate | None:
        try:
            page = await extraction.extract_url(candidate.url)
            body = (page.raw_text or "").strip()
            if len(body) < 120:
                return None
            return candidate.model_copy(update={
                "title": page.title or candidate.title,
                "raw_excerpt": body[:12000],
                "extraction_provider": page.extraction_provider or type(extraction).__name__,
                "provider_metadata": {
                    **candidate.provider_metadata,
                    **(page.extraction_metadata or {}),
                },
            })
        except Exception:
            return None

    extracted = await asyncio.gather(*[extract(item) for item in candidates[:3]])
    candidates = [item for item in extracted if item is not None]
    if not candidates:
        raise RuntimeError("remote extraction returned no readable pages")
    synthesis = await llm.complete_structured(
        [ChatMessage(role="user", content=f"""
根据以下真实网页正文形成 ResearchSynthesis。每个 finding 只能引用 candidate_id，不能创造 ID。
任务：{work_order.objective}
材料：{json.dumps([{
    'candidate_id': item.candidate_id,
    'title': item.title,
    'url': item.url,
    'excerpt': item.raw_excerpt[:1800],
} for item in candidates], ensure_ascii=False)}
""".strip())],
        ResearchSynthesis,
    )
    allowed = {item.candidate_id for item in candidates}
    findings = [
        item.model_copy(update={"evidence_ids": [value for value in item.evidence_ids if value in allowed]})
        for item in synthesis.findings
    ]
    findings = [item for item in findings if item.evidence_ids]
    evidence_ids = list(dict.fromkeys(value for item in findings for value in item.evidence_ids))
    return AgentDeliverable(
        task_id=work_order.id,
        mission_id=work_order.mission_id,
        agent_id="ecosystem_researcher_a2a",
        summary=synthesis.summary,
        findings=findings,
        evidence_ids=evidence_ids,
        evidence_candidates=candidates,
        usage=DeliverableUsage(
            steps=2,
            search_calls=len(queries),
            provider_requests=provider_requests,
            extraction_requests=len(candidates),
            llm_calls=2,
        ),
    )


def _build_worker_providers():
    """Use the same local runtime configuration surface as the main API."""

    database_path = Path(os.getenv("SECTORBREAKER_DB_PATH", "data/sectorbreaker.sqlite3"))
    config = load_runtime_config(get_runtime_config_path(database_path))
    if config.get("llm_base_url") and config.get("llm_api_key") and config.get("llm_model"):
        llm = build_llm_provider_from_config(
            base_url=config["llm_base_url"],
            api_key=config["llm_api_key"],
            model=config["llm_model"],
            max_tokens=int(config.get("llm_max_tokens", 4096)),
        )
    else:
        llm = build_llm_provider()
    search = build_search_provider_from_config(
        provider_mode=config.get("search_provider_mode", os.getenv("SEARCH_PROVIDER_MODE", "auto")),
        tavily_api_key=config.get("tavily_api_key", os.getenv("TAVILY_API_KEY")),
        tavily_endpoint=config.get("tavily_endpoint", os.getenv("TAVILY_ENDPOINT", "https://api.tavily.com/search")),
        serper_api_key=config.get("serper_api_key", os.getenv("SERPER_API_KEY")),
        serper_endpoint=config.get("serper_endpoint", os.getenv("SERPER_ENDPOINT", "https://google.serper.dev/search")),
        brave_api_key=config.get("brave_api_key", os.getenv("BRAVE_API_KEY")),
        brave_endpoint=config.get("brave_endpoint", os.getenv("BRAVE_ENDPOINT", "https://api.search.brave.com/res/v1/web/search")),
        exa_api_key=config.get("exa_api_key", os.getenv("EXA_API_KEY")),
        exa_endpoint=config.get("exa_endpoint", os.getenv("EXA_ENDPOINT", "https://api.exa.ai/search")),
        firecrawl_api_key=config.get("firecrawl_api_key", os.getenv("FIRECRAWL_API_KEY")),
        firecrawl_search_endpoint=config.get("firecrawl_search_endpoint", os.getenv("FIRECRAWL_SEARCH_ENDPOINT", "https://api.firecrawl.dev/v2/search")),
    ) or build_search_provider()
    extraction = build_content_extraction_provider_from_config(
        provider_name=config.get("content_extraction_provider", os.getenv("CONTENT_EXTRACTION_PROVIDER", "http")),
        firecrawl_api_key=config.get("firecrawl_api_key", os.getenv("FIRECRAWL_API_KEY")),
        firecrawl_endpoint=config.get("firecrawl_endpoint", os.getenv("FIRECRAWL_ENDPOINT", "https://api.firecrawl.dev/v1/scrape")),
        jina_reader_endpoint_prefix=config.get("jina_reader_endpoint_prefix", os.getenv("JINA_READER_ENDPOINT_PREFIX", "https://r.jina.ai/http://")),
    ) or build_content_extraction_provider()
    return llm, search, extraction


def create_worker_app() -> FastAPI:
    public_url = os.getenv("SECTORBREAKER_A2A_PUBLIC_URL", "http://127.0.0.1:8011/a2a")
    card = AgentCard(
        name="SectorBreaker A2A Ecosystem Researcher",
        description="Real web research Specialist returning typed evidence candidates.",
        supported_interfaces=[AgentInterface(
            url=public_url,
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        )],
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        skills=[AgentSkill(
            id="research_ecosystem",
            name="Research Ecosystem",
            description="Research participants, applications, relationships, and contested claims.",
            tags=["research_ecosystem", "web_search", "evidence_extract"],
            input_modes=["application/json"],
            output_modes=["application/json"],
        )],
    )
    handler = DefaultRequestHandler(
        agent_executor=EcosystemResearcherExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = FastAPI(title="SectorBreaker A2A Ecosystem Researcher")
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/a2a"),
    )
    return app


load_local_env()
app = create_worker_app()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("SECTORBREAKER_A2A_PORT", "8011")))
