"""FastAPI app factory."""

import asyncio
import json
import os
import subprocess
import sys
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
from backend.app.documents import extract_uploaded_document_text
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
from backend.app.graph.planner import build_agent_kernel_workflow_definition, build_workflow_definition
from backend.app.providers.factory import (
    build_content_extraction_provider,
    build_content_extraction_provider_from_config,
    build_job_source_provider,
    build_job_source_provider_from_config,
    build_llm_provider,
    build_llm_provider_from_config,
    build_search_provider,
    build_search_provider_from_config,
    build_source_registry,
)
from backend.app.providers.interfaces import (
    ChatMessage,
    ContentExtractionProvider,
    JobSourceProvider,
    JobSourceQuery,
    LLMProvider,
    SearchProvider,
    SearchQuery,
)
from backend.app.providers.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.providers.source_packs import SourceConnector, SourceRegistry
from backend.app.providers.source_verification import HeuristicSourceVerificationProvider
from backend.app.rag import ProjectRetriever
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    ProjectMode,
    ProjectDocumentCreate,
    ResearchProjectCreate,
    ResearchRun,
    ResumeRequest,
    RunArtifactSummary,
    RunEvent,
    RunProgress,
    RunSnapshot,
    RunStatus,
    UserInput,
    V1RunStage,
)
from backend.app.storage.sqlite import SQLiteRepository, init_database
from backend.app.talent_demand.pipeline import run_talent_demand_pipeline
from backend.app.agent_kernel import run_v2_agent_kernel_pipeline

LEGACY_PERSONAL_RUN_MARKERS = (
    "specialist_react_loop",
    "Knowledge Builder",
    "Document Writer",
    "L1 本源与需求 Agent",
    "L2 角色与玩家 Agent",
    "L3 原理与实操 Agent",
    "L4 商业与激励 Agent",
    "L5 风险与边界 Agent",
    "EV-V1-",
    "ART-V1-",
    "已使用保底",
)


def assert_no_legacy_personal_run_event(event: RunEvent) -> None:
    """Fail closed if archived V1/fixed-V2 workflow markers reach personal runs."""

    fields = [
        event.gate or "",
        event.step or "",
        event.agent or "",
        event.message or "",
        json.dumps(event.data, ensure_ascii=False) if event.data else "",
    ]
    payload = "\n".join(fields)
    for marker in LEGACY_PERSONAL_RUN_MARKERS:
        if marker in payload:
            raise RuntimeError(f"legacy event blocked: {marker}")


class ChatRequest(BaseModel):
    question: str


class OpenExportFolderRequest(BaseModel):
    export_dir: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[str]
    citation_details: list[dict] = Field(default_factory=list)


class FollowUpResponse(ChatResponse):
    artifact_id: str | None = None
    artifact_path: str | None = None
    updated_artifact_count: int = 0


class RagAnswerPayload(BaseModel):
    answer: str = ""
    citations: list[str] = Field(default_factory=list)


class LLMConfig(BaseModel):
    base_url: str
    api_key: str
    model: str
    max_tokens: int = Field(default=4096, ge=512, le=32768)


class LLMConfigStatus(BaseModel):
    configured: bool
    base_url: str | None = None
    model: str | None = None
    max_tokens: int | None = None


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


class JobSourceConfig(BaseModel):
    enabled: bool = False
    provider: str = "disabled"
    boss_agent_cli_command: str = "boss"
    boss_agent_cli_args_template: str | None = None
    boss_agent_cli_timeout_seconds: int = Field(default=45, ge=5, le=180)
    boss_keyword: str | None = None
    boss_city: str | None = None
    boss_limit: int = Field(default=8, ge=1, le=30)


class JobSourceTestRequest(BaseModel):
    keyword: str
    city: str | None = None
    limit: int = Field(default=3, ge=1, le=10)


class JobSourceTestResult(BaseModel):
    success: bool
    message: str
    status: dict
    result_count: int = 0
    results: list[dict] = Field(default_factory=list)


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


class SourceConnectorStatus(BaseModel):
    key: str
    display_name: str
    connector_type: str
    source_type: str
    trust_level: str
    domains: list[str] = Field(default_factory=list)
    required_env_keys: list[str] = Field(default_factory=list)
    configured: bool = False
    setup_url: str | None = None
    can_support_facts: bool = True
    requires_manual_review: bool = False
    notes: str = ""


class SourcePackStatus(BaseModel):
    name: str
    display_name: str
    market_scopes: list[str]
    reliable_domains: list[str]
    blocked_domains: list[str]
    connectors: list[SourceConnectorStatus] = Field(default_factory=list)


class SourceRegistryStatus(BaseModel):
    packs: list[SourcePackStatus] = Field(default_factory=list)
    configured_connector_count: int = 0
    recommended_next_action: str = ""


class UserInputPayload(BaseModel):
    gate: str
    input_type: str  # note | guidance | evidence_data
    content: str


ALLOWED_DOCUMENT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
ALLOWED_DOCUMENT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".docx",
    ".pdf",
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


def _build_run_snapshot(
    run: ResearchRun,
    events: list[RunEvent],
    artifacts: list[Artifact],
) -> RunSnapshot:
    latest_event = events[-1] if events else None
    progress_current = latest_event.progress_current if latest_event and latest_event.progress_current is not None else 0
    progress_total = latest_event.progress_total if latest_event and latest_event.progress_total is not None else 0
    updated_at = run.completed_at or (
        datetime.fromtimestamp(latest_event.timestamp, tz=UTC)
        if latest_event
        else run.created_at
    )
    errors = [
        event
        for event in events
        if event.event_type == "error" or event.severity in {"error", "critical"}
    ]
    return RunSnapshot(
        run_id=run.id,
        project_id=run.project_id,
        status=_v1_stage_from_run(run),
        current_stage=run.current_gate or (latest_event.gate if latest_event else "idle"),
        progress=RunProgress(
            current=progress_current,
            total=progress_total,
        ),
        events=events,
        errors=errors,
        artifact_summary=[
            RunArtifactSummary(
                id=artifact.id,
                title=artifact.title,
                content_path=artifact.content_path,
                artifact_type=artifact.artifact_type.value,
            )
            for artifact in artifacts
        ],
        updated_at=updated_at,
    )


def _v1_stage_from_run(run: ResearchRun) -> V1RunStage:
    if run.status == RunStatus.COMPLETED:
        return V1RunStage.COMPLETED
    if run.status == RunStatus.FAILED:
        return V1RunStage.FAILED
    if run.status == RunStatus.PENDING:
        return V1RunStage.IDLE
    gate = run.current_gate or ""
    if "export" in gate:
        return V1RunStage.EXPORTING
    if any(marker in gate for marker in ("knowledge", "artifact", "structur", "analysis", "map")):
        return V1RunStage.STRUCTURING
    return V1RunStage.COLLECTING


def _connector_configured(connector: SourceConnector, active_search_config: SearchConfig) -> bool:
    runtime_key_presence = {
        "TAVILY_API_KEY": bool(active_search_config.tavily_api_key),
        "SERPER_API_KEY": bool(active_search_config.serper_api_key),
        "BRAVE_API_KEY": bool(active_search_config.brave_api_key),
        "EXA_API_KEY": bool(active_search_config.exa_api_key),
        "FIRECRAWL_API_KEY": bool(active_search_config.firecrawl_api_key),
    }
    if not connector.required_env_keys:
        return True
    return all(runtime_key_presence.get(key, bool(os.getenv(key))) for key in connector.required_env_keys)


def _job_source_query_for_project(domain: str, config: JobSourceConfig) -> JobSourceQuery:
    return JobSourceQuery(
        keyword=(config.boss_keyword or domain).strip(),
        city=config.boss_city.strip() if config.boss_city else None,
        limit=config.boss_limit,
        filters={},
    )


def _job_source_status_dict(status) -> dict:
    return {
        "provider": status.provider,
        "configured": status.configured,
        "available": status.available,
        "message": status.message,
        "diagnostics": status.diagnostics or [],
    }


def _fallback_rag_answer(question: str, citation_details: list[dict]) -> str:
    lines = [f"基于当前项目资料，针对“{question}”可以先看以下证据："]
    for item in citation_details[:4]:
        lines.append(f"- {item['title']}：{item['snippet']} [{item['source_id']}]")
    lines.append("如果需要更严格的结论，建议继续补充高质量来源或重新运行研究。")
    return "\n".join(lines)


def _safe_followup_slug(value: str, max_length: int = 48) -> str:
    cleaned = "".join(char if char.isalnum() or "\u4e00" <= char <= "\u9fff" else "-" for char in value)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return (cleaned[:max_length].strip("-") or "follow-up").lower()


def _followup_title(question: str) -> str:
    question = " ".join(question.split())
    return question[:42] + ("..." if len(question) > 42 else "")


def _render_followup_artifact_content(
    *,
    project_title: str,
    question: str,
    answer: str,
    citation_details: list[dict],
) -> str:
    citation_lines = []
    for item in citation_details:
        source = item.get("source_id", "")
        title = item.get("title", source)
        source_type = item.get("source_type", "source")
        snippet = str(item.get("snippet") or "").strip()
        citation_lines.append(f"- **{title}** `{source_type}` `{source}`")
        if snippet:
            citation_lines.append(f"  - 摘要：{snippet[:260]}")
    if not citation_lines:
        citation_lines.append("- 当前项目资料未检索到足够相关引用，本页应作为待补证问题保留。")

    return "\n".join([
        f"# {_followup_title(question)}",
        "",
        "> 本页由 SectorBreaker 的项目 RAG / Living Vault 增长功能生成，表示用户在已有知识库上的一次追问与补库。",
        "",
        "## 用户追问",
        "",
        question,
        "",
        "## Agent 回答",
        "",
        answer,
        "",
        "## 引用与上下文",
        "",
        *citation_lines,
        "",
        "## 建议写回知识库的位置",
        "",
        f"- 回到 `[[{project_title} 知识库首页]]` 或主文档，判断是否需要把本页链接到相关概念、工具、风险或待验证问题。",
        "- 如果本页解释了一个新概念，建议后续拆成 `concepts/` 下的独立卡片。",
        "- 如果本页仍缺证据，下一轮应优先补充高可信来源，再更新本页。",
    ])


def _open_local_folder(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])


def create_app(
    database_path: Path,
    export_root: Path,
    search_provider: SearchProvider | None = None,
    content_extraction_provider: ContentExtractionProvider | None = None,
    job_source_provider: JobSourceProvider | None = None,
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
    active_job_source_config = JobSourceConfig(
        enabled=bool(runtime_config.get("job_source_enabled", False)),
        provider=runtime_config.get("job_source_provider", os.getenv("JOB_SOURCE_PROVIDER", "disabled")),
        boss_agent_cli_command=runtime_config.get("boss_agent_cli_command", os.getenv("BOSS_AGENT_CLI_COMMAND", "boss")),
        boss_agent_cli_args_template=runtime_config.get("boss_agent_cli_args_template", os.getenv("BOSS_AGENT_CLI_ARGS_TEMPLATE")),
        boss_agent_cli_timeout_seconds=int(runtime_config.get(
            "boss_agent_cli_timeout_seconds",
            os.getenv("BOSS_AGENT_CLI_TIMEOUT_SECONDS", "45"),
        )),
        boss_keyword=runtime_config.get("boss_keyword"),
        boss_city=runtime_config.get("boss_city"),
        boss_limit=int(runtime_config.get("boss_limit", 8)),
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
    active_job_source_provider = (
        job_source_provider
        if job_source_provider is not None
        else build_job_source_provider_from_config(
            provider_name=active_job_source_config.provider,
            boss_agent_cli_command=active_job_source_config.boss_agent_cli_command,
            boss_agent_cli_args_template=active_job_source_config.boss_agent_cli_args_template,
            boss_agent_cli_timeout_seconds=active_job_source_config.boss_agent_cli_timeout_seconds,
        )
    )
    if llm_provider is not None:
        active_llm_provider = llm_provider
    elif runtime_config.get("llm_base_url") and runtime_config.get("llm_api_key") and runtime_config.get("llm_model"):
        active_llm_provider = build_llm_provider_from_config(
            base_url=runtime_config["llm_base_url"],
            api_key=runtime_config["llm_api_key"],
            model=runtime_config["llm_model"],
            max_tokens=int(runtime_config.get("llm_max_tokens", 4096)),
        )
    else:
        active_llm_provider = build_llm_provider()
    source_registry = build_source_registry()
    source_verifier = HeuristicSourceVerificationProvider(source_registry=source_registry)
    project_retriever = ProjectRetriever(repository)
    injected_job_source_provider = job_source_provider is not None
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

    @app.get("/api/projects/{project_id}/active-run")
    def get_project_active_run(project_id: str):
        try:
            repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        run = repository.get_active_run(project_id) or repository.get_latest_run(project_id)
        if run is None:
            return None
        return run.model_dump(mode="json")

    @app.get("/api/projects/{project_id}/workflow-definition")
    def get_workflow_definition(project_id: str):
        try:
            project = repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        if project.project_mode == ProjectMode.DOMAIN_KNOWLEDGE:
            return build_agent_kernel_workflow_definition().model_dump(mode="json")
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
            if project.project_mode == ProjectMode.DOMAIN_KNOWLEDGE and auto_run:
                assert_no_legacy_personal_run_event(event)
            repository.add_run_event(event, run.id)
            repository.update_run(
                run.id,
                current_gate=event.gate,
                current_step=event.step,
            )

        async def run_in_background() -> None:
            try:
                if auto_run:
                    if project.project_mode == ProjectMode.TALENT_DEMAND:
                        job_query = _job_source_query_for_project(project.domain, active_job_source_config)
                        await run_talent_demand_pipeline(
                            project=project,
                            repository=repository,
                            search_provider=active_search_provider,
                            llm_provider=active_llm_provider,
                            job_source_provider=active_job_source_provider if active_job_source_config.enabled else None,
                            job_source_query=job_query if active_job_source_config.enabled else None,
                            emit=emit_event,
                        )
                    else:
                        await run_v2_agent_kernel_pipeline(
                            project=project,
                            repository=repository,
                            search_provider=active_search_provider,
                            llm_provider=active_llm_provider,
                            emit=emit_event,
                        )
                    repository.update_run(
                        run.id,
                        status=RunStatus.COMPLETED,
                        current_gate="completed",
                        completed_at=datetime.now(UTC),
                    )
                    return

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
                error_message = str(exc)
                safe_message = (
                    "legacy event blocked: archived personal workflow event was rejected"
                    if error_message.startswith("legacy event blocked:")
                    else f"工作流执行失败：{error_message}"
                )
                repository.add_run_event(RunEvent(
                    event_type="error",
                    gate="agent_decide" if error_message.startswith("legacy event blocked:") else "unknown",
                    agent="V2 Agent Kernel",
                    message=safe_message,
                    severity="error",
                ), run.id)
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

    @app.get("/api/runs/{run_id}/snapshot")
    def get_run_snapshot(run_id: str):
        try:
            run = repository.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        events = repository.list_run_events(run_id)
        artifacts = repository.list_artifacts(run.project_id)
        return _build_run_snapshot(run, events, artifacts).model_dump(mode="json")

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
        if plan is None:
            try:
                project = repository.get_project(run.project_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="project not found") from exc
            if project.project_mode == ProjectMode.DOMAIN_KNOWLEDGE:
                return build_agent_kernel_workflow_definition().model_dump(mode="json")
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
            existing = repository.list_run_event_records(run_id, after_id=0)
            for event_id, event in existing:
                yield f"data: {event.model_dump_json()}\n\n"
                last_id = event_id

            # If run is already done (or waiting), close after replay
            if run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
                yield "data: [DONE]\n\n"
                return

            # Poll for new events
            idle_count = 0
            max_idle = 600  # 5 minutes timeout at 0.5s intervals
            while idle_count < max_idle:
                await asyncio.sleep(0.5)
                new_events = repository.list_run_event_records(run_id, after_id=last_id)
                if new_events:
                    idle_count = 0
                    for event_id, event in new_events:
                        yield f"data: {event.model_dump_json()}\n\n"
                        last_id = event_id
                else:
                    idle_count += 1

                # Check if run completed or paused
                try:
                    current_run = repository.get_run(run_id)
                    if current_run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
                        remaining = repository.list_run_event_records(run_id, after_id=last_id)
                        for event_id, event in remaining:
                            yield f"data: {event.model_dump_json()}\n\n"
                            last_id = event_id
                        yield "data: [DONE]\n\n"
                        return
                    if current_run.status == RunStatus.WAITING_FOR_HUMAN:
                        # Drain remaining events but DON'T send [DONE]
                        remaining = repository.list_run_event_records(run_id, after_id=last_id)
                        for event_id, event in remaining:
                            yield f"data: {event.model_dump_json()}\n\n"
                            last_id = event_id
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
            content = extract_uploaded_document_text(file.filename, file.content_type, raw_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        latest_run = repository.get_latest_run(project_id)
        run_events = repository.list_run_events(latest_run.id) if latest_run is not None else []
        return exporter.export_project(project, artifacts, evidence, run_events=run_events).model_dump(mode="json")

    @app.post("/api/exports/open-folder")
    def open_export_folder(payload: OpenExportFolderRequest):
        export_root_resolved = export_root.resolve()
        target = Path(payload.export_dir).resolve()
        if target != export_root_resolved and export_root_resolved not in target.parents:
            raise HTTPException(status_code=400, detail="export folder must be inside configured export root")
        if not target.exists() or not target.is_dir():
            raise HTTPException(status_code=404, detail="export folder not found")
        try:
            _open_local_folder(target)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"failed to open export folder: {type(exc).__name__}") from exc
        return {"success": True, "export_dir": str(target)}

    # ── Chat ──────────────────────────────────────────────────────

    async def _answer_project_question(project_id: str, question: str) -> ChatResponse:
        citations = project_retriever.retrieve(project_id, question, limit=6)
        citation_ids = [item.source_id for item in citations]
        citation_details = [
            {
                "source_id": item.source_id,
                "source_type": item.source_type,
                "title": item.title,
                "snippet": item.snippet,
                "score": item.score,
                "url": item.url,
            }
            for item in citations
        ]
        if not citations:
            return ChatResponse(
                answer="当前项目资料中没有检索到足够相关的内容。建议先补充 JD、外部报告或重新运行研究。",
                citations=[],
                citation_details=[],
            )

        fallback_answer = _fallback_rag_answer(question, citation_details)
        if active_llm_provider is None:
            return ChatResponse(
                answer=fallback_answer,
                citations=citation_ids,
                citation_details=citation_details,
            )

        context = "\n\n".join(
            f"[{item['source_id']}] {item['title']} ({item['source_type']})\n{item['snippet']}"
            for item in citation_details
        )
        prompt = (
            "你是 SectorBreaker 的项目 RAG 问答 Agent。只能基于给定项目资料回答；"
            "如果资料不足，要明确说不足。回答要结构化、具体，并在关键句后标注引用 ID。\n\n"
            f"问题：{question}\n\n项目资料：\n{context}"
        )
        try:
            generated = await active_llm_provider.complete_structured(
                [ChatMessage(role="user", content=prompt)],
                RagAnswerPayload,
            )
            answer = generated.answer or fallback_answer
            generated_citations = [item for item in generated.citations if item in citation_ids]
            return ChatResponse(
                answer=answer,
                citations=generated_citations or citation_ids,
                citation_details=citation_details,
            )
        except Exception:
            return ChatResponse(
                answer=fallback_answer,
                citations=citation_ids,
                citation_details=citation_details,
            )

    @app.post("/api/projects/{project_id}/chat")
    async def chat(project_id: str, payload: ChatRequest):
        try:
            repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc

        return (await _answer_project_question(project_id, payload.question)).model_dump(mode="json")

    @app.post("/api/projects/{project_id}/follow-up")
    async def follow_up(project_id: str, payload: ChatRequest):
        try:
            project = repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc

        question = payload.question.strip()
        if not question:
            raise HTTPException(status_code=400, detail="question is required")

        answer = await _answer_project_question(project_id, question)
        now = datetime.now(UTC)
        title = f"追问：{_followup_title(question)}"
        slug = _safe_followup_slug(question)
        artifact = Artifact(
            id=f"ART-FOLLOWUP-{uuid4().hex[:12]}",
            project_id=project.id,
            artifact_type=ArtifactType.FOLLOW_UP_NOTE,
            title=title,
            content_path=f"followups/{now.strftime('%Y%m%d-%H%M%S')}-{slug}.md",
            content=_render_followup_artifact_content(
                project_title=project.title,
                question=question,
                answer=answer.answer,
                citation_details=answer.citation_details,
            ),
            source_evidence_ids=answer.citations,
            schema_version="living-vault-followup-v1",
            created_at=now,
        )
        repository.add_artifact(artifact)

        latest_run = repository.get_latest_run(project_id)
        if latest_run is not None:
            repository.add_run_event(
                RunEvent(
                    event_type="artifact_created",
                    gate="human_feedback",
                    agent="Living Vault Agent",
                    message=f"已根据追问补库：{title}",
                    data={"artifact_id": artifact.id, "content_path": artifact.content_path},
                ),
                latest_run.id,
            )

        return FollowUpResponse(
            answer=answer.answer,
            citations=answer.citations,
            citation_details=answer.citation_details,
            artifact_id=artifact.id,
            artifact_path=artifact.content_path,
            updated_artifact_count=len(repository.list_artifacts(project_id)),
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
            max_tokens=getattr(active_llm_provider, "max_tokens", None),
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
        persisted_config = load_runtime_config(runtime_config_path)
        save_runtime_config(
            runtime_config_path,
            {
                **persisted_config,
                **payload.model_dump(mode="json"),
            },
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

    @app.get("/api/config/job-source")
    async def get_job_source_config():
        status = await active_job_source_provider.status()
        return {
            **_job_source_status_dict(status),
            "enabled": active_job_source_config.enabled,
            "boss_keyword": active_job_source_config.boss_keyword,
            "boss_city": active_job_source_config.boss_city,
            "boss_limit": active_job_source_config.boss_limit,
        }

    @app.post("/api/config/job-source")
    async def update_job_source_config(payload: JobSourceConfig):
        nonlocal active_job_source_config, active_job_source_provider
        active_job_source_config = payload
        persisted_config = load_runtime_config(runtime_config_path)
        save_runtime_config(
            runtime_config_path,
            {
                **persisted_config,
                "job_source_enabled": payload.enabled,
                "job_source_provider": payload.provider,
                "boss_agent_cli_command": payload.boss_agent_cli_command,
                "boss_agent_cli_args_template": payload.boss_agent_cli_args_template,
                "boss_agent_cli_timeout_seconds": payload.boss_agent_cli_timeout_seconds,
                "boss_keyword": payload.boss_keyword,
                "boss_city": payload.boss_city,
                "boss_limit": payload.boss_limit,
            },
        )
        if not injected_job_source_provider:
            active_job_source_provider = build_job_source_provider_from_config(
                provider_name=payload.provider,
                boss_agent_cli_command=payload.boss_agent_cli_command,
                boss_agent_cli_args_template=payload.boss_agent_cli_args_template,
                boss_agent_cli_timeout_seconds=payload.boss_agent_cli_timeout_seconds,
            )
        status = await active_job_source_provider.status()
        return {
            "success": True,
            "message": status.message,
            "status": _job_source_status_dict(status),
        }

    @app.post("/api/config/job-source/test")
    async def test_job_source(payload: JobSourceTestRequest):
        status = await active_job_source_provider.status()
        if not status.available:
            return JobSourceTestResult(
                success=False,
                message=status.message,
                status=_job_source_status_dict(status),
            ).model_dump(mode="json")
        jobs = await active_job_source_provider.search_jobs(JobSourceQuery(
            keyword=payload.keyword,
            city=payload.city,
            limit=payload.limit,
        ))
        return JobSourceTestResult(
            success=bool(jobs),
            message=f"采集到 {len(jobs)} 条职位样本" if jobs else "未采集到职位样本",
            status=_job_source_status_dict(status),
            result_count=len(jobs),
            results=[
                {
                    "title": item.title,
                    "company": item.company,
                    "location": item.location,
                    "salary_text": item.salary_text,
                    "experience_text": item.experience_text,
                    "url": item.url,
                }
                for item in jobs[: payload.limit]
            ],
        ).model_dump(mode="json")

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

    @app.get("/api/config/sources")
    def get_source_registry_status():
        packs = []
        configured_count = 0
        for pack in source_registry.packs:
            connectors = []
            for connector in pack.connectors:
                configured = _connector_configured(connector, active_search_config)
                configured_count += int(configured)
                connectors.append(SourceConnectorStatus(
                    key=connector.key,
                    display_name=connector.display_name,
                    connector_type=connector.connector_type.value,
                    source_type=connector.source_type.value,
                    trust_level=connector.trust_level,
                    domains=list(connector.domains),
                    required_env_keys=list(connector.required_env_keys),
                    configured=configured,
                    setup_url=connector.setup_url,
                    can_support_facts=connector.can_support_facts,
                    requires_manual_review=connector.requires_manual_review,
                    notes=connector.notes,
                ))
            packs.append(SourcePackStatus(
                name=pack.name,
                display_name=pack.display_name,
                market_scopes=list(pack.market_scopes),
                reliable_domains=[rule.domain for rule in pack.reliable_rules],
                blocked_domains=list(pack.blocked_domains),
                connectors=connectors,
            ))
        return SourceRegistryStatus(
            packs=packs,
            configured_connector_count=configured_count,
            recommended_next_action=(
                "先配置 Tavily、Serper、Brave 或 Exa 任意一个搜索 Key，再用可靠信源自检验证域名约束。"
                if active_search_provider is None
                else "搜索已可用；可继续验证 reliable_only 策略下的权威域名结果。"
            ),
        ).model_dump(mode="json")

    @app.post("/api/config/llm")
    def update_llm_config(payload: LLMConfig):
        nonlocal active_llm_provider
        try:
            active_llm_provider = build_llm_provider_from_config(
                base_url=payload.base_url,
                api_key=payload.api_key,
                model=payload.model,
                max_tokens=payload.max_tokens,
            )
            persisted_config = load_runtime_config(runtime_config_path)
            save_runtime_config(
                runtime_config_path,
                {
                    **persisted_config,
                    "llm_base_url": payload.base_url,
                    "llm_api_key": payload.api_key,
                    "llm_model": payload.model,
                    "llm_max_tokens": payload.max_tokens,
                },
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
                max_tokens=payload.max_tokens,
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
