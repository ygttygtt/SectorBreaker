"""FastAPI app factory."""

import asyncio
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.background import BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.app.env import load_local_env
from backend.app.config_store import get_runtime_config_path, load_runtime_config, save_runtime_config
from backend.app.exporters.markdown import MarkdownExporter
from backend.app.evidence_builder import citation_to_evidence
from backend.app.graph.workflow import (
    search_constraints_for_policy,
    _state_from_json,
    _state_to_json,
    _to_research_state,
    next_gate,
    run_research_workflow,
    run_workflow_until_pause,
)
from backend.app.graph.planner import build_workflow_definition
from backend.app.providers.factory import (
    build_content_extraction_provider,
    build_content_extraction_provider_from_config,
    build_llm_provider,
    build_llm_provider_from_config,
    build_search_provider,
    build_search_provider_from_config,
)
from backend.app.providers.interfaces import ContentExtractionProvider, LLMProvider, SearchProvider, SearchQuery
from backend.app.providers.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.providers.source_verification import HeuristicSourceVerificationProvider
from backend.app.schemas import (
    ProjectDocumentCreate,
    ResearchProjectCreate,
    ResearchRun,
    ResumeRequest,
    RunEvent,
    RunStatus,
    UserInput,
)
from backend.app.storage.sqlite import SQLiteRepository, init_database


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[str]


class LLMConfig(BaseModel):
    base_url: str
    api_key: str
    model: str


class LLMConfigStatus(BaseModel):
    configured: bool
    base_url: str | None = None
    model: str | None = None


class SearchConfigStatus(BaseModel):
    configured: bool
    provider: str | None = None
    providers: list[str] = Field(default_factory=list)
    requested_provider_mode: str = "auto"
    extraction_provider: str | None = None
    extraction_providers: list[str] = Field(default_factory=list)
    requested_extraction_provider: str | None = None
    missing_configuration: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    status_message: str = ""


class SearchConfig(BaseModel):
    search_provider_mode: str = "auto"
    tavily_api_key: str | None = None
    tavily_endpoint: str = "https://api.tavily.com/search"
    serper_api_key: str | None = None
    serper_endpoint: str = "https://google.serper.dev/search"
    brave_api_key: str | None = None
    brave_endpoint: str = "https://api.search.brave.com/res/v1/web/search"
    exa_api_key: str | None = None
    exa_endpoint: str = "https://api.exa.ai/search"
    content_extraction_provider: str = "http"
    firecrawl_api_key: str | None = None
    firecrawl_endpoint: str = "https://api.firecrawl.dev/v1/scrape"
    jina_reader_endpoint_prefix: str = "https://r.jina.ai/http://"


class SearchTestRequest(BaseModel):
    query: str
    url_to_extract: str | None = None
    market_scope: str = "mixed"
    source_policy: str = "open_web"
    max_results: int = 3
    auto_extract_first_result: bool = True
    allowed_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)


class SearchTestResult(BaseModel):
    success: bool
    message: str
    source_policy: str = "open_web"
    providers: list[str] = Field(default_factory=list)
    effective_allowed_domains: list[str] = Field(default_factory=list)
    effective_blocked_domains: list[str] = Field(default_factory=list)
    result_count: int = 0
    results: list[dict] = Field(default_factory=list)
    extracted_page: dict | None = None
    source_assessment: dict | None = None


class LLMTestResult(BaseModel):
    success: bool
    message: str


class UserInputPayload(BaseModel):
    gate: str
    input_type: str  # note | guidance | evidence_data
    content: str


ALLOWED_DOCUMENT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
}
ALLOWED_DOCUMENT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
}


def _validate_document_upload(file_name: str | None, mime_type: str | None) -> None:
    suffix = Path(file_name or "").suffix.lower()
    if suffix and suffix not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="unsupported document extension")
    if mime_type and mime_type not in ALLOWED_DOCUMENT_MIME_TYPES:
        raise HTTPException(status_code=400, detail="unsupported document mime type")


def _search_provider_names(active_search_provider: SearchProvider | None) -> list[str]:
    if active_search_provider is None:
        return []
    aggregated_providers = getattr(active_search_provider, "providers", None)
    if aggregated_providers:
        return [
            type(provider).__name__.removesuffix("SearchProvider").lower() or "search"
            for provider in aggregated_providers
        ]
    return [type(active_search_provider).__name__.removesuffix("SearchProvider").lower() or "search"]


def _extraction_provider_names(active_content_extraction_provider: ContentExtractionProvider | None) -> list[str]:
    if active_content_extraction_provider is None:
        return []
    return [
        type(active_content_extraction_provider).__name__.removesuffix("ContentExtractionProvider").lower()
        or "content_extraction"
    ]


def _normalize_extraction_provider_name(provider_name: str | None) -> str:
    normalized = (provider_name or "http").strip().lower()
    if normalized in {"jina_reader", "jinareader"}:
        return "jina"
    if normalized not in {"http", "firecrawl", "jina"}:
        return "http"
    return normalized


def _build_search_config_status(
    *,
    active_search_provider: SearchProvider | None,
    active_content_extraction_provider: ContentExtractionProvider | None,
    active_search_config: SearchConfig,
) -> SearchConfigStatus:
    providers = _search_provider_names(active_search_provider)
    extraction_providers = _extraction_provider_names(active_content_extraction_provider)
    requested_extraction_provider = _normalize_extraction_provider_name(
        active_search_config.content_extraction_provider,
    )
    requested_provider_mode = (active_search_config.search_provider_mode or "auto").strip().lower()
    missing_configuration: list[str] = []
    diagnostics: list[str] = []

    provider_key_presence = {
        "tavily": bool(active_search_config.tavily_api_key),
        "serper": bool(active_search_config.serper_api_key),
        "brave": bool(active_search_config.brave_api_key),
        "exa": bool(active_search_config.exa_api_key),
    }
    provider_key_names = {
        "tavily": "tavily_api_key",
        "serper": "serper_api_key",
        "brave": "brave_api_key",
        "exa": "exa_api_key",
    }

    if requested_provider_mode in provider_key_names:
        if not provider_key_presence[requested_provider_mode]:
            missing_configuration.append(provider_key_names[requested_provider_mode])
    elif requested_provider_mode == "multi":
        for provider_name, is_present in provider_key_presence.items():
            if not is_present:
                missing_configuration.append(provider_key_names[provider_name])
    else:
        if not any(provider_key_presence.values()):
            missing_configuration.extend(provider_key_names.values())

    if active_search_provider is None:
        diagnostics.append("至少需要配置 Tavily、Serper、Brave、Exa 四者之一的 API Key，开放网络搜索才会启用。")
    elif len(providers) > 1:
        diagnostics.append(f"当前启用了聚合搜索：{', '.join(providers)}。")
    elif requested_provider_mode in {"tavily", "serper", "brave", "exa"}:
        diagnostics.append(f"当前已强制使用单一搜索 provider：{requested_provider_mode}。")

    if requested_provider_mode == "multi" and len(providers) <= 1 and active_search_provider is not None:
        diagnostics.append("当前请求 multi 模式，但只有一个 provider 可用，因此暂时按单 provider 运行。")

    if requested_extraction_provider == "firecrawl" and not active_search_config.firecrawl_api_key:
        missing_configuration.append("firecrawl_api_key")
        diagnostics.append("已选择 Firecrawl 抽取，但缺少 FIRECRAWL_API_KEY，当前已回退到 http。")

    effective_extraction_provider = extraction_providers[0] if extraction_providers else None
    if requested_extraction_provider == "jina" and effective_extraction_provider != "jinareader":
        diagnostics.append("已请求 Jina 抽取，但当前未生效，系统已回退到默认 http 抽取。")

    status_message = (
        f"搜索已就绪：{', '.join(providers)}；抽取使用 {effective_extraction_provider or 'unknown'}。"
        if active_search_provider is not None
        else "搜索未配置：请至少填写 Tavily、Serper、Brave、Exa 四者之一的 API Key。"
    )

    return SearchConfigStatus(
        configured=active_search_provider is not None,
        provider=providers[0] if providers else None,
        providers=providers,
        requested_provider_mode=requested_provider_mode,
        extraction_provider=effective_extraction_provider,
        extraction_providers=extraction_providers,
        requested_extraction_provider=requested_extraction_provider,
        missing_configuration=missing_configuration,
        diagnostics=diagnostics,
        status_message=status_message,
    )


def _build_project_document_inputs(
    repository: SQLiteRepository,
    project_id: str,
) -> tuple[list[dict], list[dict], str | None]:
    seed_evidence_items = [
        item.model_dump(mode="json")
        for item in repository.list_evidence_by_collector(project_id, "document_citation_ingestion")
    ]

    user_evidence_items: list[dict] = []
    assistant_briefs: list[str] = []
    for document in repository.list_documents(project_id):
        if document.channel == "assistant_brief":
            assistant_briefs.append(document.content)
            continue
        user_evidence_items.append(
            {
                "id": f"DOC-{document.id}",
                "source_title": document.file_name or document.id,
                "snippet": document.content[:1200],
                "summary": "用户上传文档，作为研究线索与上下文补充。",
                "confidence": 0.7,
            }
        )

    assistant_brief = "\n\n".join(assistant_briefs).strip() or None
    return seed_evidence_items, user_evidence_items, assistant_brief


def create_app(
    database_path: Path,
    export_root: Path,
    search_provider: SearchProvider | None = None,
    content_extraction_provider: ContentExtractionProvider | None = None,
    llm_provider: LLMProvider | None = None,
) -> FastAPI:
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    runtime_config_path = get_runtime_config_path(database_path)
    exporter = MarkdownExporter(export_root)
    runtime_config = load_runtime_config(runtime_config_path)
    active_search_config = SearchConfig(
        search_provider_mode=runtime_config.get("search_provider_mode", os.getenv("SEARCH_PROVIDER_MODE", "auto")),
        tavily_api_key=runtime_config.get("tavily_api_key", os.getenv("TAVILY_API_KEY")),
        tavily_endpoint=runtime_config.get("tavily_endpoint", os.getenv("TAVILY_ENDPOINT", "https://api.tavily.com/search")),
        serper_api_key=runtime_config.get("serper_api_key", os.getenv("SERPER_API_KEY")),
        serper_endpoint=runtime_config.get("serper_endpoint", os.getenv("SERPER_ENDPOINT", "https://google.serper.dev/search")),
        brave_api_key=runtime_config.get("brave_api_key", os.getenv("BRAVE_API_KEY")),
        brave_endpoint=runtime_config.get("brave_endpoint", os.getenv("BRAVE_ENDPOINT", "https://api.search.brave.com/res/v1/web/search")),
        exa_api_key=runtime_config.get("exa_api_key", os.getenv("EXA_API_KEY")),
        exa_endpoint=runtime_config.get("exa_endpoint", os.getenv("EXA_ENDPOINT", "https://api.exa.ai/search")),
        content_extraction_provider=runtime_config.get(
            "content_extraction_provider",
            os.getenv("CONTENT_EXTRACTION_PROVIDER", "http"),
        ),
        firecrawl_api_key=runtime_config.get("firecrawl_api_key", os.getenv("FIRECRAWL_API_KEY")),
        firecrawl_endpoint=runtime_config.get("firecrawl_endpoint", os.getenv("FIRECRAWL_ENDPOINT", "https://api.firecrawl.dev/v1/scrape")),
        jina_reader_endpoint_prefix=runtime_config.get("jina_reader_endpoint_prefix", os.getenv("JINA_READER_ENDPOINT_PREFIX", "https://r.jina.ai/http://")),
    )
    active_search_provider = (
        search_provider
        if search_provider is not None
        else build_search_provider_from_config(
            provider_mode=active_search_config.search_provider_mode,
            tavily_api_key=active_search_config.tavily_api_key,
            tavily_endpoint=active_search_config.tavily_endpoint,
            serper_api_key=active_search_config.serper_api_key,
            serper_endpoint=active_search_config.serper_endpoint,
            brave_api_key=active_search_config.brave_api_key,
            brave_endpoint=active_search_config.brave_endpoint,
            exa_api_key=active_search_config.exa_api_key,
            exa_endpoint=active_search_config.exa_endpoint,
        )
    )
    active_content_extraction_provider = (
        content_extraction_provider
        if content_extraction_provider is not None
        else build_content_extraction_provider_from_config(
            provider_name=active_search_config.content_extraction_provider,
            firecrawl_api_key=active_search_config.firecrawl_api_key,
            firecrawl_endpoint=active_search_config.firecrawl_endpoint,
            jina_reader_endpoint_prefix=active_search_config.jina_reader_endpoint_prefix,
        )
    )
    active_llm_provider = llm_provider if llm_provider is not None else build_llm_provider()
    source_verifier = HeuristicSourceVerificationProvider()
    app = FastAPI(title="SectorBreaker")

    # ── Projects ──────────────────────────────────────────────────

    @app.post("/api/projects")
    def create_project(payload: ResearchProjectCreate):
        return repository.create_project(payload).model_dump(mode="json")

    @app.get("/api/projects")
    def list_projects():
        return [project.model_dump(mode="json") for project in repository.list_projects()]

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str):
        try:
            return repository.get_project(project_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc

    @app.get("/api/projects/{project_id}/workflow-definition")
    def get_workflow_definition(project_id: str):
        try:
            repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        definition = build_workflow_definition()
        return definition.model_dump(mode="json")

    # ── Runs ──────────────────────────────────────────────────────

    @app.post("/api/projects/{project_id}/runs")
    async def run_project(project_id: str, background_tasks: BackgroundTasks, auto_run: bool = False):
        """Create a run and start the workflow in the background.

        The workflow runs gates sequentially. After each gate that requires
        human review, it pauses and sets status to waiting_for_human.
        """
        try:
            project = repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc

        run = repository.create_run(project_id)
        repository.update_run(run.id, status=RunStatus.RUNNING)
        seed_evidence_items, document_user_evidence_items, document_assistant_brief = _build_project_document_inputs(
            repository,
            project_id,
        )

        async def emit_event(event: RunEvent) -> None:
            repository.add_run_event(event, run.id)

        async def run_in_background() -> None:
            try:
                state, paused_gate, completed = await run_workflow_until_pause(
                    project,
                    search_provider=active_search_provider,
                    content_extraction_provider=active_content_extraction_provider,
                    llm_provider=active_llm_provider,
                    emitter=emit_event,
                    seed_evidence_items=seed_evidence_items or None,
                    user_evidence_items=document_user_evidence_items or None,
                    assistant_brief=document_assistant_brief,
                    auto_run=auto_run,
                )

                # Persist workflow state
                repository.update_run(run.id, workflow_state=_state_to_json(state))

                if completed:
                    # All gates finished — persist results
                    research_state = _to_research_state(state)
                    for evidence in research_state.evidence:
                        repository.add_evidence(evidence)
                    for artifact in research_state.artifacts:
                        repository.add_artifact(artifact)
                    repository.update_run(
                        run.id,
                        status=RunStatus.COMPLETED,
                        completed_at=datetime.now(UTC),
                    )
                elif paused_gate:
                    # Paused for human review
                    repository.update_run(
                        run.id,
                        status=RunStatus.WAITING_FOR_HUMAN,
                        current_gate=paused_gate,
                    )
                    await emit_event(RunEvent(
                        event_type="waiting_for_human",
                        gate=paused_gate,
                        message=f"等待人工审阅：{paused_gate}",
                    ))
            except Exception as exc:
                await emit_event(RunEvent(
                    event_type="error", gate="unknown",
                    message=f"工作流执行失败：{exc}",
                ))
                repository.update_run(run.id, status=RunStatus.FAILED, completed_at=datetime.now(UTC))

        background_tasks.add_task(run_in_background)
        return repository.get_run(run.id).model_dump(mode="json")

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        try:
            run = repository.get_run(run_id)
            data = run.model_dump(mode="json")
            # Don't expose workflow_state to frontend
            data.pop("workflow_state", None)
            return data
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

    @app.get("/api/runs/{run_id}/workflow-definition")
    def get_run_workflow_definition(run_id: str):
        try:
            run = repository.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        plan = None
        if run.workflow_state:
            raw_state = _state_from_json(run.workflow_state)
            if raw_state.get("supervisor_plan"):
                from backend.app.schemas import SupervisorPlan
                plan = SupervisorPlan(**raw_state["supervisor_plan"])
        return build_workflow_definition(plan).model_dump(mode="json")

    @app.post("/api/runs/{run_id}/resume")
    async def resume_run(run_id: str, payload: ResumeRequest, background_tasks: BackgroundTasks):
        """Resume workflow after human review.

        Stores user inputs and continues execution from the next gate.
        """
        try:
            run = repository.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

        if run.status != RunStatus.WAITING_FOR_HUMAN:
            raise HTTPException(status_code=400, detail=f"run is not waiting for human review (status: {run.status})")

        # Store user inputs
        if payload.guidance:
            repository.add_user_input(UserInput(
                id=f"ui-{uuid4().hex}",
                run_id=run_id,
                gate=run.current_gate or "unknown",
                input_type="guidance",
                content=payload.guidance,
            ))
        if payload.evidence_data:
            repository.add_user_input(UserInput(
                id=f"ui-{uuid4().hex}",
                run_id=run_id,
                gate=run.current_gate or "unknown",
                input_type="evidence_data",
                content=payload.evidence_data,
            ))
        if payload.assistant_brief:
            repository.add_user_input(UserInput(
                id=f"ui-{uuid4().hex}",
                run_id=run_id,
                gate=run.current_gate or "unknown",
                input_type="assistant_brief",
                content=payload.assistant_brief,
            ))

        # Load workflow state and resume
        try:
            project = repository.get_project(run.project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc

        state = _state_from_json(run.workflow_state) if run.workflow_state else None
        seed_evidence_items, document_user_evidence_items, document_assistant_brief = _build_project_document_inputs(
            repository,
            project.id,
        )

        repository.update_run(run_id, status=RunStatus.RUNNING)

        async def emit_event(event: RunEvent) -> None:
            repository.add_run_event(event, run_id)

        async def resume_in_background() -> None:
            try:
                user_inputs = repository.list_user_inputs(run_id)
                guidance = "\n".join(
                    f"[{inp.gate}] {inp.content}" for inp in user_inputs if inp.input_type == "guidance"
                )
                evidence_items = [
                    {"source_title": "用户补充", "snippet": inp.content}
                    for inp in user_inputs if inp.input_type == "evidence_data"
                ]
                evidence_items.extend(document_user_evidence_items)
                assistant_brief = "\n\n".join(
                    inp.content for inp in user_inputs if inp.input_type == "assistant_brief"
                )
                if document_assistant_brief:
                    assistant_brief = (
                        f"{document_assistant_brief}\n\n{assistant_brief}".strip()
                        if assistant_brief
                        else document_assistant_brief
                    )

                new_state, paused_gate, completed = await run_workflow_until_pause(
                    project,
                    search_provider=active_search_provider,
                    content_extraction_provider=active_content_extraction_provider,
                    llm_provider=active_llm_provider,
                    emitter=emit_event,
                    state=state,
                    user_guidance=guidance or None,
                    user_evidence_items=evidence_items or None,
                    seed_evidence_items=seed_evidence_items or None,
                    assistant_brief=assistant_brief or None,
                )

                repository.update_run(run_id, workflow_state=_state_to_json(new_state))

                if completed:
                    research_state = _to_research_state(new_state)
                    for evidence in research_state.evidence:
                        repository.add_evidence(evidence)
                    for artifact in research_state.artifacts:
                        repository.add_artifact(artifact)
                    repository.update_run(
                        run_id,
                        status=RunStatus.COMPLETED,
                        completed_at=datetime.now(UTC),
                    )
                elif paused_gate:
                    repository.update_run(
                        run_id,
                        status=RunStatus.WAITING_FOR_HUMAN,
                        current_gate=paused_gate,
                    )
                    await emit_event(RunEvent(
                        event_type="waiting_for_human",
                        gate=paused_gate,
                        message=f"等待人工审阅：{paused_gate}",
                    ))
            except Exception as exc:
                await emit_event(RunEvent(
                    event_type="error", gate="unknown",
                    message=f"工作流恢复失败：{exc}",
                ))
                repository.update_run(run_id, status=RunStatus.FAILED, completed_at=datetime.now(UTC))

        background_tasks.add_task(resume_in_background)

        return {"status": "resumed", "run_id": run_id}

    @app.get("/api/runs/{run_id}/events")
    async def stream_events(run_id: str):
        """SSE endpoint for streaming run events."""
        try:
            run = repository.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

        async def event_generator():
            last_id = 0
            # First, replay any events that were stored before SSE connected
            existing = repository.list_run_events(run_id, after_id=0)
            for event in existing:
                yield f"data: {event.model_dump_json()}\n\n"
                last_id += 1

            # If run is already done (or waiting), close after replay
            if run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
                yield "data: [DONE]\n\n"
                return

            # Poll for new events
            idle_count = 0
            max_idle = 600  # 5 minutes timeout at 0.5s intervals
            while idle_count < max_idle:
                await asyncio.sleep(0.5)
                new_events = repository.list_run_events(run_id, after_id=last_id)
                if new_events:
                    idle_count = 0
                    for event in new_events:
                        yield f"data: {event.model_dump_json()}\n\n"
                        last_id += 1
                else:
                    idle_count += 1

                # Check if run completed or paused
                try:
                    current_run = repository.get_run(run_id)
                    if current_run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
                        remaining = repository.list_run_events(run_id, after_id=last_id)
                        for event in remaining:
                            yield f"data: {event.model_dump_json()}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    if current_run.status == RunStatus.WAITING_FOR_HUMAN:
                        # Drain remaining events but DON'T send [DONE]
                        remaining = repository.list_run_events(run_id, after_id=last_id)
                        for event in remaining:
                            yield f"data: {event.model_dump_json()}\n\n"
                        # Keep connection open — workflow is paused
                        # Continue polling for when resume is called
                        idle_count = 0
                except KeyError:
                    yield "data: [DONE]\n\n"
                    return

            yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/runs/{run_id}/inputs")
    async def add_user_input_endpoint(run_id: str, payload: UserInputPayload):
        """Add supplementary user input at any point."""
        try:
            repository.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

        user_input = UserInput(
            id=f"ui-{uuid4().hex}",
            run_id=run_id,
            gate=payload.gate,
            input_type=payload.input_type,
            content=payload.content,
        )
        repository.add_user_input(user_input)
        return {"status": "ok", "input_id": user_input.id}

    # ── Evidence & Artifacts ──────────────────────────────────────

    @app.get("/api/projects/{project_id}/evidence")
    def list_evidence(project_id: str):
        return [item.model_dump(mode="json") for item in repository.list_evidence(project_id)]

    @app.get("/api/projects/{project_id}/artifacts")
    def list_artifacts(project_id: str):
        return [item.model_dump(mode="json") for item in repository.list_artifacts(project_id)]

    @app.post("/api/projects/{project_id}/documents")
    def create_document(project_id: str, payload: ProjectDocumentCreate):
        try:
            repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        return repository.add_document(project_id, payload).model_dump(mode="json")

    @app.post("/api/projects/{project_id}/documents/upload")
    async def upload_document(
        project_id: str,
        channel: str = Form(...),
        file: UploadFile = File(...),
    ):
        try:
            repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc

        _validate_document_upload(file.filename, file.content_type)
        raw_bytes = await file.read()
        try:
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="document must be utf-8 text") from exc

        payload = ProjectDocumentCreate(
            channel=channel,
            content=content,
            file_name=file.filename,
            mime_type=file.content_type,
        )
        return repository.add_document(project_id, payload).model_dump(mode="json")

    @app.get("/api/projects/{project_id}/documents")
    def list_documents(project_id: str):
        return [item.model_dump(mode="json") for item in repository.list_documents(project_id)]

    @app.get("/api/documents/{document_id}")
    def get_document(document_id: str):
        try:
            return repository.get_document(document_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="document not found") from exc

    @app.get("/api/documents/{document_id}/segments")
    def list_document_segments(document_id: str):
        try:
            repository.get_document(document_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="document not found") from exc
        return [item.model_dump(mode="json") for item in repository.list_document_segments(document_id)]

    @app.get("/api/documents/{document_id}/citations")
    async def list_document_citations(document_id: str):
        try:
            document = repository.get_document(document_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="document not found") from exc
        citations = repository.list_document_citations(document_id)
        assessed = []
        for citation in citations:
            assessment = await source_verifier.assess_source(
                url=citation.source_url,
                title=citation.source_title,
                snippet=None,
                extracted_text=None,
                source_policy=repository.get_project(document.project_id).source_policy.value,
            )
            assessed.append(
                {
                    **citation.model_dump(mode="json"),
                    "source_assessment": {
                        "source_type": assessment.source_type,
                        "source_quality": assessment.source_quality,
                        "is_original_source": assessment.is_original_source,
                        "is_marketing_like": assessment.is_marketing_like,
                        "domain": assessment.domain,
                        "marketing_signals": assessment.marketing_signals or [],
                        "reliability_notes": assessment.reliability_notes,
                        "recommended_verification_status": assessment.recommended_verification_status,
                    },
                }
            )
        return assessed

    @app.get("/api/documents/{document_id}/evidence-preview")
    async def get_document_evidence_preview(document_id: str):
        try:
            document = repository.get_document(document_id)
            project = repository.get_project(document.project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="document not found") from exc

        citations = repository.list_document_citations(document_id)
        evidence_preview = []
        for index, citation in enumerate(citations, start=1):
            assessment = await source_verifier.assess_source(
                url=citation.source_url,
                title=citation.source_title,
                snippet=None,
                extracted_text=None,
                source_policy=project.source_policy.value,
            )
            evidence = citation_to_evidence(
                project_id=project.id,
                document=document,
                citation=citation,
                assessment=assessment,
                evidence_index=index,
            )
            evidence_preview.append(evidence.model_dump(mode="json"))
        return evidence_preview

    @app.post("/api/documents/{document_id}/ingest-evidence")
    async def ingest_document_evidence(document_id: str):
        try:
            document = repository.get_document(document_id)
            project = repository.get_project(document.project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="document not found") from exc

        existing = {
            item.id
            for item in repository.list_evidence_by_collector(project.id, "document_citation_ingestion")
            if item.id.startswith(f"EV-DOC-{document_id}-")
        }
        citations = repository.list_document_citations(document_id)
        created: list[dict] = []
        for index, citation in enumerate(citations, start=1):
            assessment = await source_verifier.assess_source(
                url=citation.source_url,
                title=citation.source_title,
                snippet=None,
                extracted_text=None,
                source_policy=project.source_policy.value,
            )
            evidence = citation_to_evidence(
                project_id=project.id,
                document=document,
                citation=citation,
                assessment=assessment,
                evidence_index=index,
            )
            if evidence.id in existing:
                continue
            repository.add_evidence(evidence)
            created.append(evidence.model_dump(mode="json"))

        return {
            "document_id": document_id,
            "created_count": len(created),
            "evidence": created,
        }

    # ── Export ────────────────────────────────────────────────────

    @app.post("/api/projects/{project_id}/exports")
    def export_project(project_id: str):
        try:
            project = repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        evidence = repository.list_evidence(project_id)
        artifacts = repository.list_artifacts(project_id)
        return exporter.export_project(project, artifacts, evidence).model_dump(mode="json")

    # ── Chat ──────────────────────────────────────────────────────

    @app.post("/api/projects/{project_id}/chat")
    def chat(project_id: str, payload: ChatRequest):
        results = repository.search_project(project_id, payload.question, limit=5)
        citations = [item.document_id for item in results]
        if not citations:
            citations = [item.id for item in repository.list_evidence(project_id)[:1]]
        return ChatResponse(
            answer="基于当前项目资料，建议先从研究框架、行业地图和机会假设开始。",
            citations=citations,
        ).model_dump(mode="json")

    # ── LLM Config ────────────────────────────────────────────────

    @app.get("/api/config/llm")
    def get_llm_config():
        nonlocal active_llm_provider
        if active_llm_provider is None:
            return LLMConfigStatus(configured=False).model_dump(mode="json")
        return LLMConfigStatus(
            configured=True,
            base_url=active_llm_provider.base_url,
            model=active_llm_provider.model,
        ).model_dump(mode="json")

    @app.get("/api/config/search")
    def get_search_config():
        return _build_search_config_status(
            active_search_provider=active_search_provider,
            active_content_extraction_provider=active_content_extraction_provider,
            active_search_config=active_search_config,
        ).model_dump(mode="json")

    @app.post("/api/config/search")
    def update_search_config(payload: SearchConfig):
        nonlocal active_search_provider, active_content_extraction_provider, active_search_config
        active_search_config = payload
        save_runtime_config(
            runtime_config_path,
            payload.model_dump(mode="json"),
        )
        active_search_provider = build_search_provider_from_config(
            provider_mode=payload.search_provider_mode,
            tavily_api_key=payload.tavily_api_key,
            tavily_endpoint=payload.tavily_endpoint,
            serper_api_key=payload.serper_api_key,
            serper_endpoint=payload.serper_endpoint,
            brave_api_key=payload.brave_api_key,
            brave_endpoint=payload.brave_endpoint,
            exa_api_key=payload.exa_api_key,
            exa_endpoint=payload.exa_endpoint,
        )
        active_content_extraction_provider = build_content_extraction_provider_from_config(
            provider_name=payload.content_extraction_provider,
            firecrawl_api_key=payload.firecrawl_api_key,
            firecrawl_endpoint=payload.firecrawl_endpoint,
            jina_reader_endpoint_prefix=payload.jina_reader_endpoint_prefix,
        )
        return {
            "success": True,
            "message": "搜索配置已更新",
            "configured": active_search_provider is not None,
        }

    @app.post("/api/config/search/test")
    async def test_search_connection(payload: SearchTestRequest):
        if active_search_provider is None:
            return SearchTestResult(
                success=False,
                message="未配置搜索 provider",
                source_policy=payload.source_policy,
                providers=[],
            ).model_dump(mode="json")

        providers = _search_provider_names(active_search_provider)

        try:
            policy_allowed_domains, policy_blocked_domains = search_constraints_for_policy(
                {
                    "market_scope": payload.market_scope,
                    "source_policy": payload.source_policy,
                },
                verification=True,
                preferred_domains=payload.allowed_domains,
            )
            effective_allowed_domains = payload.allowed_domains or policy_allowed_domains
            effective_blocked_domains = list(dict.fromkeys(payload.blocked_domains + policy_blocked_domains))
            results = await active_search_provider.search(
                SearchQuery(
                    query=payload.query,
                    market_scope=payload.market_scope,
                    max_results=payload.max_results,
                    allowed_domains=effective_allowed_domains,
                    blocked_domains=effective_blocked_domains,
                )
            )
            extracted_page = None
            extract_target = payload.url_to_extract
            if not extract_target and payload.auto_extract_first_result and results:
                extract_target = results[0].url

            source_assessment = None
            if extract_target:
                page = await active_content_extraction_provider.extract_url(extract_target)
                first_result = next((item for item in results if item.url == extract_target), None)
                assessment = await source_verifier.assess_source(
                    url=page.canonical_url or page.url,
                    title=page.title or (first_result.title if first_result else None),
                    snippet=first_result.snippet if first_result else None,
                    extracted_text=page.raw_text,
                    source_policy=payload.source_policy,
                )
                extracted_page = {
                    "url": page.url,
                    "canonical_url": page.canonical_url,
                    "title": page.title,
                    "domain": page.domain,
                    "extraction_provider": page.extraction_provider,
                    "raw_text_preview": page.raw_text[:500],
                }
                source_assessment = {
                    "source_type": assessment.source_type,
                    "source_quality": assessment.source_quality,
                    "is_original_source": assessment.is_original_source,
                    "is_marketing_like": assessment.is_marketing_like,
                    "domain": assessment.domain,
                    "recommended_verification_status": assessment.recommended_verification_status,
                    "reliability_notes": assessment.reliability_notes,
                }

            return SearchTestResult(
                success=True,
                message="搜索/抽取链路可用",
                source_policy=payload.source_policy,
                providers=providers,
                effective_allowed_domains=effective_allowed_domains,
                effective_blocked_domains=effective_blocked_domains,
                result_count=len(results),
                results=[
                    {
                        "title": item.title,
                        "url": item.url,
                        "snippet": item.snippet,
                        "published_date": item.published_date,
                        "provider_metadata": item.provider_metadata,
                    }
                    for item in results
                ],
                extracted_page=extracted_page,
                source_assessment=source_assessment,
            ).model_dump(mode="json")
        except Exception as exc:
            return SearchTestResult(
                success=False,
                message=f"搜索/抽取测试失败: {exc}",
                source_policy=payload.source_policy,
                providers=providers,
                effective_allowed_domains=effective_allowed_domains,
                effective_blocked_domains=effective_blocked_domains,
            ).model_dump(mode="json")

    @app.post("/api/config/llm")
    def update_llm_config(payload: LLMConfig):
        nonlocal active_llm_provider
        try:
            active_llm_provider = build_llm_provider_from_config(
                base_url=payload.base_url,
                api_key=payload.api_key,
                model=payload.model,
            )
            return {"success": True, "message": "LLM 配置已更新"}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/config/llm/test")
    async def test_llm_connection(payload: LLMConfig):
        try:
            provider = OpenAICompatibleLLMProvider(
                base_url=payload.base_url,
                api_key=payload.api_key,
                model=payload.model,
            )
            from backend.app.providers.interfaces import ChatMessage
            messages = [ChatMessage(role="user", content="Hello")]
            await provider.complete_structured(messages, str)
            return LLMTestResult(success=True, message="连接成功").model_dump(mode="json")
        except Exception as exc:
            return LLMTestResult(success=False, message=f"连接失败: {str(exc)}").model_dump(mode="json")

    return app


load_local_env()

app = create_app(
    database_path=Path(os.getenv("SECTORBREAKER_DB_PATH", "data/sectorbreaker.sqlite3")),
    export_root=Path(os.getenv("SECTORBREAKER_EXPORT_ROOT", "exports")),
)
