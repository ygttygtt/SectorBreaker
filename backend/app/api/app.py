"""FastAPI app factory."""

import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
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
from backend.app.agent_kernel.workflow_definition import build_agent_kernel_workflow_definition
from backend.app.providers.factory import (
    build_content_extraction_provider,
    build_content_extraction_provider_from_config,
    build_embedding_provider,
    build_llm_provider,
    build_llm_provider_from_config,
    build_search_provider,
    build_search_provider_from_config,
    build_source_registry,
)
from backend.app.providers.interfaces import (
    ChatMessage,
    ContentExtractionProvider,
    EmbeddingProvider,
    LLMProvider,
    SearchProvider,
    SearchQuery,
)
from backend.app.providers.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.providers.catalog import PROVIDER_ONBOARDING
from backend.app.providers.source_packs import SourceConnector, SourceConnectorType, SourceRegistry
from backend.app.providers.source_policy import search_constraints_for_policy, url_matches_domain_policy
from backend.app.providers.source_verification import HeuristicSourceVerificationProvider
from backend.app.rag import ProjectRetriever
from backend.app.knowledge_base import ChangeSetService, VaultKnowledgeService
from backend.app.agent_state.models import AutonomyPolicy
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    ProjectDocumentCreate,
    ProjectSourcePreferences,
    ResearchProjectCreate,
    ResearchProjectUpdate,
    ResearchRun,
    ResumeRequest,
    RunArtifactSummary,
    RunEvent,
    RunProgress,
    RunSnapshot,
    RunStatus,
    SourcePolicy,
    UserInput,
    ChangeSetProposalRequest,
    MaintenanceRunRequest,
    VaultImportRequest,
)
from backend.app.storage.sqlite import SQLiteRepository, init_database
from backend.app.agent_kernel import run_v2_agent_kernel_pipeline
from backend.app.agent_kernel.models import KernelRunResult, KernelRunStatus

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

RUN_LEASE_SECONDS = 90


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


def _finalize_kernel_run(
    repository: SQLiteRepository,
    run_id: str,
    result: KernelRunResult,
    *,
    lease_owner_id: str,
) -> None:
    if result.status == KernelRunStatus.COMPLETED:
        repository.finish_owned_run(
            run_id,
            lease_owner_id=lease_owner_id,
            status=RunStatus.COMPLETED,
            current_gate="completed",
            terminal_reason=result.stop_reason,
        )
        return
    if result.status == KernelRunStatus.WAITING_FOR_HUMAN:
        repository.add_run_event(
            RunEvent(
                event_type="waiting_for_human",
                gate="human_feedback",
                agent="V3 Master Agent",
                message=result.stop_reason or "Agent 等待用户确认后继续。",
                data={
                    "reason": result.stop_reason,
                    "checkpoint_available": repository.has_run_state_checkpoint(run_id),
                    "can_resume": True,
                },
                severity="warning",
            ),
            run_id,
            lease_owner_id=lease_owner_id,
            lease_seconds=RUN_LEASE_SECONDS,
        )
        repository.finish_owned_run(
            run_id,
            lease_owner_id=lease_owner_id,
            status=RunStatus.WAITING_FOR_HUMAN,
            current_gate="human_feedback",
            terminal_reason=result.stop_reason,
        )
        return
    repository.finish_owned_run(
        run_id,
        lease_owner_id=lease_owner_id,
        status=RunStatus.FAILED,
        current_gate=result.status.value,
        terminal_reason=result.stop_reason,
    )


def _reconcile_and_record_stale_runs(repository: SQLiteRepository) -> list[ResearchRun]:
    reconciled = repository.reconcile_stale_runs()
    for stale_run in reconciled:
        repository.add_run_event(
            RunEvent(
                event_type="run_interrupted" if stale_run.status == RunStatus.INTERRUPTED else "error",
                gate=stale_run.current_gate or "unknown",
                agent="Run Recovery",
                message=(
                    "运行进程已失联；检测到 durable checkpoint，可创建恢复运行。"
                    if stale_run.status == RunStatus.INTERRUPTED
                    else "运行进程已失联，且没有 durable checkpoint，无法恢复。"
                ),
                data={
                    "terminal_reason": stale_run.terminal_reason,
                    "can_recover": stale_run.status == RunStatus.INTERRUPTED,
                },
                severity="warning" if stale_run.status == RunStatus.INTERRUPTED else "error",
            ),
            stale_run.id,
        )
    return reconciled


class ChatRequest(BaseModel):
    question: str


class OpenExportFolderRequest(BaseModel):
    export_dir: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[str]
    citation_details: list[dict] = Field(default_factory=list)
    retrieval_mode: str = "lexical"
    embedding_model: str | None = None
    retrieval_diagnostics: dict = Field(default_factory=dict)


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


class LLMPresetPayload(BaseModel):
    name: str
    base_url: str = ""
    api_key: str | None = None
    model: str = ""
    max_tokens: int = Field(default=4096, ge=512, le=32768)
    notes: str | None = None


class LLMPresetApplyPayload(BaseModel):
    api_key: str | None = None


class LLMConfigStatus(BaseModel):
    configured: bool
    base_url: str | None = None
    model: str | None = None
    max_tokens: int | None = None


class ProviderOnboardingStatus(BaseModel):
    key: str
    display_name: str
    capability: str
    signup_url: str | None = None
    pricing_url: str | None = None
    requires_api_key: bool
    free_tier_summary: str
    configured: bool = False
    selected: bool = False


class SearchConfigStatus(BaseModel):
    configured: bool
    provider: str | None = None
    providers: list[str] = Field(default_factory=list)
    requested_provider_mode: str = "auto"
    extraction_provider: str | None = None
    extraction_providers: list[str] = Field(default_factory=list)
    requested_extraction_provider: str | None = None
    configured_api_keys: list[str] = Field(default_factory=list)
    missing_configuration: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    status_message: str = ""
    provider_onboarding: list[ProviderOnboardingStatus] = Field(default_factory=list)


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
    firecrawl_search_endpoint: str = "https://api.firecrawl.dev/v2/search"
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


class SourceConnectorStatus(BaseModel):
    key: str
    display_name: str
    connector_type: str
    source_type: str
    trust_level: str
    domains: list[str] = Field(default_factory=list)
    required_env_keys: list[str] = Field(default_factory=list)
    configured: bool = False
    execution_status: str = "planned"
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


def _validate_project_source_packs(
    payload: ProjectSourcePreferences,
    source_registry: SourceRegistry,
) -> None:
    known_pack_ids = {pack.name for pack in source_registry.packs}
    unknown = sorted(set(payload.source_pack_ids) - known_pack_ids)
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown source pack ids: {', '.join(unknown)}")


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


DEFAULT_LLM_PRESETS: dict[str, dict] = {
    "deepseek-official": {
        "id": "deepseek-official",
        "name": "DeepSeek 官方",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "max_tokens": 4096,
        "notes": "OpenAI-compatible DeepSeek endpoint. Fill your local key before applying.",
    },
    "sensenova-v4-flash": {
        "id": "sensenova-v4-flash",
        "name": "商汤 V4 Flash",
        "base_url": "https://token.sensenova.cn/v1",
        "model": "deepseek-v4-flash",
        "max_tokens": 4096,
        "notes": "SenseNova OpenAI-compatible runtime preset. API key stays local.",
    },
    "mimo": {
        "id": "mimo",
        "name": "Mimo",
        "base_url": "",
        "model": "mimo-v2.5-pro",
        "max_tokens": 4096,
        "notes": "Fill the local Mimo-compatible base URL and key before applying.",
    },
}


def _llm_presets_from_runtime(runtime_config: dict) -> dict[str, dict]:
    stored = runtime_config.get("llm_presets")
    if not isinstance(stored, dict):
        stored = {}
    presets = {preset_id: dict(preset) for preset_id, preset in DEFAULT_LLM_PRESETS.items()}
    for preset_id, preset in stored.items():
        if isinstance(preset, dict):
            merged = {**presets.get(preset_id, {"id": preset_id}), **preset, "id": preset_id}
            presets[preset_id] = merged
    return presets


def _public_llm_preset(preset_id: str, preset: dict) -> dict:
    return {
        "id": preset_id,
        "name": str(preset.get("name") or preset_id),
        "base_url": str(preset.get("base_url") or ""),
        "model": str(preset.get("model") or ""),
        "max_tokens": int(preset.get("max_tokens") or 4096),
        "notes": preset.get("notes"),
        "has_api_key": bool(preset.get("api_key")),
        "is_builtin": preset_id in DEFAULT_LLM_PRESETS,
    }


def _save_llm_presets_to_runtime(runtime_config_path: Path, presets: dict[str, dict]) -> None:
    persisted_config = load_runtime_config(runtime_config_path)
    save_runtime_config(
        runtime_config_path,
        {
            **persisted_config,
            "llm_presets": presets,
        },
    )


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
        "firecrawl": bool(active_search_config.firecrawl_api_key),
    }
    provider_key_names = {
        "tavily": "tavily_api_key",
        "serper": "serper_api_key",
        "brave": "brave_api_key",
        "exa": "exa_api_key",
        "firecrawl": "firecrawl_api_key",
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
        diagnostics.append("至少需要配置 Tavily、Serper、Brave、Exa 或 Firecrawl 之一的 API Key，开放网络搜索才会启用。")
    elif len(providers) > 1:
        diagnostics.append(f"当前启用了聚合搜索：{', '.join(providers)}。")
    elif requested_provider_mode in {"tavily", "serper", "brave", "exa", "firecrawl"}:
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
        else "搜索未配置：请至少填写 Tavily、Serper、Brave、Exa 或 Firecrawl 之一的 API Key。"
    )
    onboarding_status = []
    for provider in PROVIDER_ONBOARDING:
        configured = (
            provider_key_presence.get(provider.key, False)
            if provider.requires_api_key
            else True
        )
        selected_for_search = provider.key in providers
        selected_for_extraction = provider.key == _normalize_extraction_provider_name(
            effective_extraction_provider,
        )
        onboarding_status.append(ProviderOnboardingStatus(
            **asdict(provider),
            configured=configured,
            selected=selected_for_search or selected_for_extraction,
        ))

    return SearchConfigStatus(
        configured=active_search_provider is not None,
        provider=providers[0] if providers else None,
        providers=providers,
        requested_provider_mode=requested_provider_mode,
        extraction_provider=effective_extraction_provider,
        extraction_providers=extraction_providers,
        requested_extraction_provider=requested_extraction_provider,
        configured_api_keys=[name for name, present in provider_key_presence.items() if present],
        missing_configuration=missing_configuration,
        diagnostics=diagnostics,
        status_message=status_message,
        provider_onboarding=onboarding_status,
    )


def _build_run_snapshot(
    repository: SQLiteRepository,
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
        status=run.status,
        current_stage=run.current_gate or (latest_event.gate if latest_event else "idle"),
        terminal_reason=run.terminal_reason,
        resumed_from_run_id=run.resumed_from_run_id,
        can_resume=(
            run.status == RunStatus.WAITING_FOR_HUMAN
            and repository.has_run_state_checkpoint(run.id)
        ),
        can_recover=(
            run.status == RunStatus.INTERRUPTED
            and repository.has_run_state_checkpoint(run.id)
            and not repository.has_recovery_child(run.id)
        ),
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


def _connector_execution_status(
    connector: SourceConnector,
    active_search_config: SearchConfig,
    *,
    search_available: bool,
) -> str:
    runtime_key_presence = {
        "TAVILY_API_KEY": bool(active_search_config.tavily_api_key),
        "SERPER_API_KEY": bool(active_search_config.serper_api_key),
        "BRAVE_API_KEY": bool(active_search_config.brave_api_key),
        "EXA_API_KEY": bool(active_search_config.exa_api_key),
        "FIRECRAWL_API_KEY": bool(active_search_config.firecrawl_api_key),
    }
    configured = all(
        runtime_key_presence.get(key, bool(os.getenv(key)))
        for key in connector.required_env_keys
    )
    if connector.connector_type == SourceConnectorType.SEARCH_DOMAIN_PACK:
        return "available_via_domain_filter" if search_available else "needs_search_provider"
    if connector.connector_type == SourceConnectorType.EXTRACTION_FALLBACK:
        if connector.key == "firecrawl_extraction":
            if not active_search_config.firecrawl_api_key:
                return "needs_configuration"
            return (
                "ready"
                if _normalize_extraction_provider_name(active_search_config.content_extraction_provider) == "firecrawl"
                else "available_not_selected"
            )
        if connector.key == "jina_reader_extraction":
            return (
                "ready"
                if _normalize_extraction_provider_name(active_search_config.content_extraction_provider) == "jina"
                else "available_not_selected"
            )
    if connector.connector_type == SourceConnectorType.MANUAL_REVIEW:
        return "manual_review"
    # These entries document desirable direct adapters. They are not executable
    # until a provider implementation exists, even when an API key is present.
    if configured and connector.required_env_keys:
        return "configured_but_unwired"
    return "planned"


def _connector_configured(
    connector: SourceConnector,
    active_search_config: SearchConfig,
    *,
    search_available: bool,
) -> bool:
    return _connector_execution_status(
        connector,
        active_search_config,
        search_available=search_available,
    ) == "ready"


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
    llm_provider: LLMProvider | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    embedding_mode: str = "disabled",
) -> FastAPI:
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    _reconcile_and_record_stale_runs(repository)
    vault_service = VaultKnowledgeService(repository)
    change_set_service = ChangeSetService(repository)
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
        firecrawl_search_endpoint=runtime_config.get(
            "firecrawl_search_endpoint",
            os.getenv("FIRECRAWL_SEARCH_ENDPOINT", "https://api.firecrawl.dev/v2/search"),
        ),
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
            firecrawl_api_key=active_search_config.firecrawl_api_key,
            firecrawl_search_endpoint=active_search_config.firecrawl_search_endpoint,
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
    project_retriever = ProjectRetriever(
        repository,
        embedding_provider=embedding_provider,
        embedding_mode=embedding_mode,
    )
    app = FastAPI(title="SectorBreaker")

    # ── Projects ──────────────────────────────────────────────────

    @app.post("/api/projects")
    def create_project(payload: ResearchProjectCreate):
        _validate_project_source_packs(payload.source_preferences, source_registry)
        return repository.create_project(payload).model_dump(mode="json")

    @app.get("/api/projects")
    def list_projects():
        return [project.model_dump(mode="json") for project in repository.list_projects()]

    @app.patch("/api/projects/{project_id}")
    def update_project(project_id: str, payload: ResearchProjectUpdate):
        _validate_project_source_packs(payload.source_preferences, source_registry)
        try:
            project = repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        if project.status.value == "archived":
            raise HTTPException(status_code=400, detail="archived projects cannot be updated")
        return repository.update_project_source_preferences(
            project_id,
            payload.source_preferences,
        ).model_dump(mode="json")

    @app.get("/api/config/retrieval")
    def get_retrieval_status(project_id: str | None = None):
        if project_id is not None:
            try:
                repository.get_project(project_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="project not found") from exc
        return asdict(project_retriever.status(project_id))

    @app.post("/api/projects/{project_id}/retrieval/reindex")
    async def rebuild_project_retrieval_index(project_id: str):
        try:
            repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        try:
            result = await asyncio.to_thread(project_retriever.rebuild_vector_index, project_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"vector reindex failed: {type(exc).__name__}: {exc}") from exc
        return asdict(result)

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
        # Compatibility endpoint used by the frontend to restore the latest
        # run, even when it is already terminal. Admission control uses the
        # transactional create_claimed_run path instead.
        _reconcile_and_record_stale_runs(repository)
        run = repository.get_active_run(project_id) or repository.get_latest_run(project_id)
        if run is None:
            return None
        return run.model_dump(mode="json")

    @app.post("/api/projects/{project_id}/vault/import")
    def import_project_vault(project_id: str, payload: VaultImportRequest):
        try:
            project = repository.get_project(project_id)
            record = vault_service.import_vault(project, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return record.model_dump(mode="json")

    @app.get("/api/projects/{project_id}/vault")
    def get_project_vault(project_id: str):
        try:
            repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        return vault_service.status(project_id).model_dump(mode="json")

    @app.post("/api/projects/{project_id}/audits")
    def audit_project_vault(project_id: str):
        try:
            repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        report = vault_service.audit(project_id)
        return report.model_dump(mode="json")

    @app.get("/api/projects/{project_id}/health")
    def get_project_health(project_id: str):
        try:
            repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        report = repository.latest_health_report(project_id)
        if report is None:
            raise HTTPException(status_code=404, detail="knowledge health report not found")
        return report.model_dump(mode="json")

    @app.get("/api/projects/{project_id}/maintenance-backlog")
    def get_project_maintenance_backlog(project_id: str):
        try:
            repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        return [task.model_dump(mode="json") for task in repository.list_maintenance_tasks(project_id)]

    @app.post("/api/projects/{project_id}/change-sets")
    def propose_project_change_set(project_id: str, payload: ChangeSetProposalRequest):
        try:
            repository.get_project(project_id)
            change_set = change_set_service.propose(project_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project or artifact not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return change_set.model_dump(mode="json")

    @app.get("/api/projects/{project_id}/change-sets")
    def list_project_change_sets(project_id: str):
        try:
            repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        return [item.model_dump(mode="json") for item in repository.list_change_sets(project_id)]

    @app.post("/api/projects/{project_id}/change-sets/{change_set_id}/approve")
    def approve_project_change_set(project_id: str, change_set_id: str):
        try:
            existing = repository.get_change_set(change_set_id)
            if existing.project_id != project_id:
                raise KeyError(change_set_id)
            change_set = change_set_service.approve(change_set_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="change set not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return change_set.model_dump(mode="json")

    @app.post("/api/projects/{project_id}/change-sets/{change_set_id}/apply")
    def apply_project_change_set(project_id: str, change_set_id: str):
        try:
            change_set = repository.get_change_set(change_set_id)
            if change_set.project_id != project_id:
                raise KeyError(change_set_id)
            change_set = change_set_service.apply(change_set_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="change set not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return change_set.model_dump(mode="json")

    @app.post("/api/projects/{project_id}/change-sets/{change_set_id}/rollback")
    def rollback_project_change_set(project_id: str, change_set_id: str):
        try:
            change_set = repository.get_change_set(change_set_id)
            if change_set.project_id != project_id:
                raise KeyError(change_set_id)
            change_set = change_set_service.rollback(change_set_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="change set not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return change_set.model_dump(mode="json")

    @app.get("/api/projects/{project_id}/workflow-definition")
    def get_workflow_definition(project_id: str):
        try:
            project = repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        if project.status.value == "archived":
            raise HTTPException(status_code=400, detail="archived projects cannot be run")
        return build_agent_kernel_workflow_definition().model_dump(mode="json")

    # ── Runs ──────────────────────────────────────────────────────

    @app.post("/api/projects/{project_id}/runs")
    async def run_project(project_id: str, background_tasks: BackgroundTasks, auto_run: bool = False):
        """Create a run and start the Agent Kernel in the background.

        ``auto_run`` remains as a request-compatibility flag; the production
        owner is always the same Agent Kernel rather than a second workflow.
        """
        try:
            project = repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        if project.status.value == "archived":
            raise HTTPException(status_code=400, detail="archived projects cannot be run")

        _reconcile_and_record_stale_runs(repository)
        lease_owner_id = f"worker-{uuid4().hex}"
        try:
            run = repository.create_claimed_run(
                project_id,
                lease_owner_id=lease_owner_id,
                lease_seconds=RUN_LEASE_SECONDS,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        async def emit_event(event: RunEvent) -> None:
            assert_no_legacy_personal_run_event(event)
            repository.add_run_event(
                event,
                run.id,
                lease_owner_id=lease_owner_id,
                lease_seconds=RUN_LEASE_SECONDS,
            )

        async def run_in_background() -> None:
            try:
                result = await run_v2_agent_kernel_pipeline(
                    project=project,
                    repository=repository,
                    search_provider=active_search_provider,
                    content_extraction_provider=active_content_extraction_provider,
                    source_verification_provider=source_verifier,
                    llm_provider=active_llm_provider,
                    emit=emit_event,
                    run_id=run.id,
                    project_retriever=project_retriever,
                )
                _finalize_kernel_run(repository, run.id, result, lease_owner_id=lease_owner_id)
            except Exception as exc:
                error_message = str(exc)
                safe_message = (
                    "legacy event blocked: archived personal workflow event was rejected"
                    if error_message.startswith("legacy event blocked:")
                    else f"工作流执行失败：{error_message}"
                )
                try:
                    repository.add_run_event(RunEvent(
                        event_type="error",
                        gate="agent_decide" if error_message.startswith("legacy event blocked:") else "unknown",
                        agent="V3 Agent Kernel",
                        message=safe_message,
                        severity="error",
                    ), run.id, lease_owner_id=lease_owner_id, lease_seconds=RUN_LEASE_SECONDS)
                    repository.finish_owned_run(
                        run.id,
                        lease_owner_id=lease_owner_id,
                        status=RunStatus.FAILED,
                        current_gate="failed",
                        terminal_reason=error_message[:300],
                    )
                except RuntimeError:
                    return

        background_tasks.add_task(run_in_background)
        return repository.get_run(run.id).model_dump(mode="json")

    @app.post("/api/projects/{project_id}/continue")
    async def continue_project_run(project_id: str, background_tasks: BackgroundTasks):
        """Resume Agent Kernel from latest checkpoint for a second knowledge-base expansion run."""
        try:
            project = repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        if project.status.value == "archived":
            raise HTTPException(status_code=400, detail="archived projects cannot be continued")
        _reconcile_and_record_stale_runs(repository)
        resumed_state = repository.load_latest_resumable_project_checkpoint(project_id=project_id)
        if resumed_state is None:
            raise HTTPException(
                status_code=404,
                detail="no state checkpoint found — run the project at least once first",
            )
        lease_owner_id = f"worker-{uuid4().hex}"
        try:
            run = repository.create_claimed_run(
                project_id,
                lease_owner_id=lease_owner_id,
                lease_seconds=RUN_LEASE_SECONDS,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        async def emit_event_continue(event: RunEvent) -> None:
            assert_no_legacy_personal_run_event(event)
            repository.add_run_event(
                event,
                run.id,
                lease_owner_id=lease_owner_id,
                lease_seconds=RUN_LEASE_SECONDS,
            )

        async def continue_in_background() -> None:
            try:
                result = await run_v2_agent_kernel_pipeline(
                    project=project,
                    repository=repository,
                    search_provider=active_search_provider,
                    content_extraction_provider=active_content_extraction_provider,
                    source_verification_provider=source_verifier,
                    llm_provider=active_llm_provider,
                    emit=emit_event_continue,
                    run_id=run.id,
                    resume_state=resumed_state,
                    project_retriever=project_retriever,
                )
                _finalize_kernel_run(repository, run.id, result, lease_owner_id=lease_owner_id)
            except Exception as exc:
                try:
                    repository.add_run_event(RunEvent(
                        event_type="error",
                        gate="agent_decide",
                        agent="V3 Agent Kernel",
                        message=str(exc)[:800],
                        severity="error",
                    ), run.id, lease_owner_id=lease_owner_id, lease_seconds=RUN_LEASE_SECONDS)
                    repository.finish_owned_run(
                        run.id,
                        lease_owner_id=lease_owner_id,
                        status=RunStatus.FAILED,
                        current_gate="failed",
                        terminal_reason=str(exc)[:300],
                    )
                except RuntimeError:
                    return

        background_tasks.add_task(continue_in_background)
        return {"run_id": run.id, "status": "started", "resumed_from_checkpoint": True}

    @app.post("/api/projects/{project_id}/maintenance-runs")
    async def start_maintenance_run(
        project_id: str,
        payload: MaintenanceRunRequest,
        background_tasks: BackgroundTasks,
    ):
        try:
            project = repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        if project.status.value == "archived":
            raise HTTPException(status_code=400, detail="archived projects cannot be maintained")
        known_task_ids = {task.id for task in repository.list_maintenance_tasks(project_id)}
        unknown = [task_id for task_id in payload.task_ids if task_id not in known_task_ids]
        if unknown:
            raise HTTPException(status_code=400, detail={"unknown_task_ids": unknown})

        _reconcile_and_record_stale_runs(repository)
        resumed_state = repository.load_latest_resumable_project_checkpoint(project_id=project_id)
        lease_owner_id = f"worker-{uuid4().hex}"
        try:
            run = repository.create_claimed_run(
                project_id,
                lease_owner_id=lease_owner_id,
                lease_seconds=RUN_LEASE_SECONDS,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        async def emit_maintenance_event(event: RunEvent) -> None:
            assert_no_legacy_personal_run_event(event)
            repository.add_run_event(
                event,
                run.id,
                lease_owner_id=lease_owner_id,
                lease_seconds=RUN_LEASE_SECONDS,
            )

        async def maintain_in_background() -> None:
            try:
                result = await run_v2_agent_kernel_pipeline(
                    project=project,
                    repository=repository,
                    search_provider=active_search_provider,
                    content_extraction_provider=active_content_extraction_provider,
                    source_verification_provider=source_verifier,
                    llm_provider=active_llm_provider,
                    emit=emit_maintenance_event,
                    run_id=run.id,
                    resume_state=resumed_state,
                    maintenance_request=payload,
                    project_retriever=project_retriever,
                )
                _finalize_kernel_run(repository, run.id, result, lease_owner_id=lease_owner_id)
            except Exception as exc:
                try:
                    repository.add_run_event(RunEvent(
                        event_type="error",
                        gate="agent_decide",
                        agent="V3 Knowledge Manager",
                        message=str(exc)[:800],
                        severity="error",
                    ), run.id, lease_owner_id=lease_owner_id, lease_seconds=RUN_LEASE_SECONDS)
                    repository.finish_owned_run(
                        run.id,
                        lease_owner_id=lease_owner_id,
                        status=RunStatus.FAILED,
                        current_gate="failed",
                        terminal_reason=str(exc)[:300],
                    )
                except RuntimeError:
                    return

        background_tasks.add_task(maintain_in_background)
        return {
            "run_id": run.id,
            "status": "started",
            "resumed_from_checkpoint": resumed_state is not None,
            "task_ids": payload.task_ids,
            "execution_mode": payload.execution_mode,
        }

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        try:
            run = repository.get_run(run_id)
            data = run.model_dump(mode="json")
            # Internal workflow/lease ownership is not a public capability.
            data.pop("workflow_state", None)
            data.pop("lease_owner_id", None)
            return data
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

    @app.get("/api/runs/{run_id}/snapshot")
    def get_run_snapshot(run_id: str):
        _reconcile_and_record_stale_runs(repository)
        try:
            run = repository.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        events = repository.list_run_events(run_id)
        artifacts = repository.list_artifacts(run.project_id)
        return _build_run_snapshot(repository, run, events, artifacts).model_dump(mode="json")

    @app.get("/api/runs/{run_id}/workflow-definition")
    def get_run_workflow_definition(run_id: str):
        try:
            repository.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        return build_agent_kernel_workflow_definition().model_dump(mode="json")

    @app.get("/api/runs/{run_id}/trace")
    def export_run_trace(run_id: str):
        """Export the full run trace for debugging and tuning analysis."""
        try:
            run = repository.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        events = repository.list_run_events(run_id)
        return {
            "run_id": run_id,
            "project_id": run.project_id,
            "status": run.status.value,
            "event_count": len(events),
            "events": [event.model_dump(mode="json") for event in events],
        }

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
            if run.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.INTERRUPTED):
                yield "data: [DONE]\n\n"
                return

            # Poll for new events
            idle_count = 0
            while True:
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
                    if current_run.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.INTERRUPTED):
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
                if idle_count >= 30:
                    yield ": keepalive\n\n"
                    idle_count = 0

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

    @app.post("/api/runs/{run_id}/resume")
    async def resume_waiting_run(
        run_id: str,
        payload: ResumeRequest,
        background_tasks: BackgroundTasks,
    ):
        try:
            run = repository.get_run(run_id)
            project = repository.get_project(run.project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        if run.status != RunStatus.WAITING_FOR_HUMAN:
            raise HTTPException(status_code=409, detail="only waiting_for_human runs can be resumed")
        if not payload.plan_confirmed:
            raise HTTPException(status_code=400, detail="plan_confirmed must be true before resuming")
        resumed_state = repository.load_run_state_checkpoint(run_id=run_id)
        if resumed_state is None:
            raise HTTPException(status_code=409, detail="waiting run has no durable state checkpoint")

        lease_owner_id = f"worker-{uuid4().hex}"
        if not repository.claim_waiting_run(
            run_id,
            lease_owner_id=lease_owner_id,
            lease_seconds=RUN_LEASE_SECONDS,
        ):
            raise HTTPException(status_code=409, detail="waiting run was already resumed")

        for input_type, content in (
            ("guidance", payload.guidance),
            ("evidence_data", payload.evidence_data),
            ("assistant_brief", payload.assistant_brief),
        ):
            cleaned = str(content or "").strip()
            if not cleaned:
                continue
            repository.add_user_input(UserInput(
                id=f"ui-{uuid4().hex}",
                run_id=run_id,
                gate="human_feedback",
                input_type=input_type,
                content=cleaned,
            ))

        async def emit_resume_event(event: RunEvent) -> None:
            assert_no_legacy_personal_run_event(event)
            repository.add_run_event(
                event,
                run_id,
                lease_owner_id=lease_owner_id,
                lease_seconds=RUN_LEASE_SECONDS,
            )

        async def resume_in_background() -> None:
            try:
                result = await run_v2_agent_kernel_pipeline(
                    project=project,
                    repository=repository,
                    search_provider=active_search_provider,
                    content_extraction_provider=active_content_extraction_provider,
                    source_verification_provider=source_verifier,
                    llm_provider=active_llm_provider,
                    emit=emit_resume_event,
                    run_id=run_id,
                    resume_state=resumed_state,
                    resume_request=payload,
                    project_retriever=project_retriever,
                )
                _finalize_kernel_run(repository, run_id, result, lease_owner_id=lease_owner_id)
            except Exception as exc:
                try:
                    repository.add_run_event(RunEvent(
                        event_type="error",
                        gate="agent_decide",
                        agent="V3 Agent Kernel",
                        message=str(exc)[:800],
                        severity="error",
                    ), run_id, lease_owner_id=lease_owner_id, lease_seconds=RUN_LEASE_SECONDS)
                    repository.finish_owned_run(
                        run_id,
                        lease_owner_id=lease_owner_id,
                        status=RunStatus.FAILED,
                        current_gate="failed",
                        terminal_reason=str(exc)[:300],
                    )
                except RuntimeError:
                    return

        background_tasks.add_task(resume_in_background)
        return {"status": "resumed", "run_id": run_id}

    @app.post("/api/runs/{run_id}/recover")
    async def recover_interrupted_run(run_id: str, background_tasks: BackgroundTasks):
        try:
            parent = repository.get_run(run_id)
            project = repository.get_project(parent.project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        if parent.status != RunStatus.INTERRUPTED:
            raise HTTPException(status_code=409, detail="only interrupted runs can be recovered")
        resumed_state = repository.load_run_state_checkpoint(run_id=run_id)
        if resumed_state is None:
            raise HTTPException(status_code=409, detail="interrupted run has no durable state checkpoint")

        lease_owner_id = f"worker-{uuid4().hex}"
        try:
            child = repository.create_claimed_run(
                parent.project_id,
                lease_owner_id=lease_owner_id,
                lease_seconds=RUN_LEASE_SECONDS,
                resumed_from_run_id=parent.id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        async def emit_recovery_event(event: RunEvent) -> None:
            assert_no_legacy_personal_run_event(event)
            repository.add_run_event(
                event,
                child.id,
                lease_owner_id=lease_owner_id,
                lease_seconds=RUN_LEASE_SECONDS,
            )

        async def recover_in_background() -> None:
            try:
                result = await run_v2_agent_kernel_pipeline(
                    project=project,
                    repository=repository,
                    search_provider=active_search_provider,
                    content_extraction_provider=active_content_extraction_provider,
                    source_verification_provider=source_verifier,
                    llm_provider=active_llm_provider,
                    emit=emit_recovery_event,
                    run_id=child.id,
                    resume_state=resumed_state,
                    preserve_run_budget=True,
                    project_retriever=project_retriever,
                )
                _finalize_kernel_run(repository, child.id, result, lease_owner_id=lease_owner_id)
            except Exception as exc:
                try:
                    repository.add_run_event(RunEvent(
                        event_type="error",
                        gate="agent_decide",
                        agent="V3 Agent Kernel Recovery",
                        message=str(exc)[:800],
                        severity="error",
                    ), child.id, lease_owner_id=lease_owner_id, lease_seconds=RUN_LEASE_SECONDS)
                    repository.finish_owned_run(
                        child.id,
                        lease_owner_id=lease_owner_id,
                        status=RunStatus.FAILED,
                        current_gate="failed",
                        terminal_reason=str(exc)[:300],
                    )
                except RuntimeError:
                    return

        background_tasks.add_task(recover_in_background)
        return {
            "status": "recovery_started",
            "run_id": child.id,
            "resumed_from_run_id": parent.id,
        }

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
        agent_state = repository.load_latest_resumable_project_checkpoint(project_id=project_id)
        health_snapshot = repository.latest_health_report(project_id)
        maintenance_backlog = repository.list_maintenance_tasks(project_id)
        change_sets = repository.list_change_sets(project_id)
        return exporter.export_project(
            project,
            artifacts,
            evidence,
            run_events=run_events,
            agent_state=agent_state,
            health_snapshot=health_snapshot,
            maintenance_backlog=maintenance_backlog,
            change_sets=change_sets,
        ).model_dump(mode="json")

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
        citations, diagnostics = await asyncio.to_thread(
            project_retriever.retrieve_with_diagnostics,
            project_id,
            question,
            6,
        )
        citation_ids = [item.source_id for item in citations]
        citation_details = [
            {
                "source_id": item.source_id,
                "parent_id": item.parent_id,
                "source_type": item.source_type,
                "title": item.title,
                "snippet": item.snippet,
                "score": item.score,
                "url": item.url,
                "relative_path": item.relative_path,
                "content_hash": item.content_hash,
                "verification_status": item.verification_status,
                "retrieval_mode": item.retrieval_mode,
                "lexical_rank": item.lexical_rank,
                "vector_rank": item.vector_rank,
                "lexical_score": item.lexical_score,
                "vector_score": item.vector_score,
                "embedding_model": item.embedding_model,
            }
            for item in citations
        ]
        if not citations:
            return ChatResponse(
                answer="当前项目资料中没有检索到足够相关的内容。建议先补充 JD、外部报告或重新运行研究。",
                citations=[],
                citation_details=[],
                retrieval_mode=diagnostics.effective_mode,
                embedding_model=diagnostics.embedding_model,
                retrieval_diagnostics=asdict(diagnostics),
            )

        fallback_answer = _fallback_rag_answer(question, citation_details)
        if active_llm_provider is None:
            return ChatResponse(
                answer=fallback_answer,
                citations=citation_ids,
                citation_details=citation_details,
                retrieval_mode=diagnostics.effective_mode,
                embedding_model=diagnostics.embedding_model,
                retrieval_diagnostics=asdict(diagnostics),
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
                retrieval_mode=diagnostics.effective_mode,
                embedding_model=diagnostics.embedding_model,
                retrieval_diagnostics=asdict(diagnostics),
            )
        except Exception:
            return ChatResponse(
                answer=fallback_answer,
                citations=citation_ids,
                citation_details=citation_details,
                retrieval_mode=diagnostics.effective_mode,
                embedding_model=diagnostics.embedding_model,
                retrieval_diagnostics=asdict(diagnostics),
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
            retrieval_mode=answer.retrieval_mode,
            embedding_model=answer.embedding_model,
            retrieval_diagnostics=answer.retrieval_diagnostics,
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

    @app.get("/api/config/llm/presets")
    def list_llm_presets():
        presets = _llm_presets_from_runtime(load_runtime_config(runtime_config_path))
        return {
            "presets": [
                _public_llm_preset(preset_id, preset)
                for preset_id, preset in sorted(presets.items(), key=lambda item: item[1].get("name", item[0]))
            ],
        }

    @app.put("/api/config/llm/presets/{preset_id}")
    def upsert_llm_preset(preset_id: str, payload: LLMPresetPayload):
        normalized_id = preset_id.strip()
        if not normalized_id:
            raise HTTPException(status_code=400, detail="preset id is required")
        presets = _llm_presets_from_runtime(load_runtime_config(runtime_config_path))
        current = presets.get(normalized_id, {"id": normalized_id})
        next_preset = {
            **current,
            "id": normalized_id,
            "name": payload.name.strip() or normalized_id,
            "base_url": payload.base_url.strip(),
            "model": payload.model.strip(),
            "max_tokens": payload.max_tokens,
            "notes": payload.notes,
        }
        if payload.api_key is not None:
            next_preset["api_key"] = payload.api_key
        presets[normalized_id] = next_preset
        _save_llm_presets_to_runtime(runtime_config_path, presets)
        return {"success": True, "preset": _public_llm_preset(normalized_id, next_preset)}

    @app.delete("/api/config/llm/presets/{preset_id}")
    def delete_llm_preset(preset_id: str):
        if preset_id in DEFAULT_LLM_PRESETS:
            raise HTTPException(status_code=400, detail="built-in presets cannot be deleted")
        presets = _llm_presets_from_runtime(load_runtime_config(runtime_config_path))
        if preset_id not in presets:
            raise HTTPException(status_code=404, detail="preset not found")
        del presets[preset_id]
        _save_llm_presets_to_runtime(runtime_config_path, presets)
        return {"success": True, "message": "LLM 预设已删除"}

    @app.post("/api/config/llm/presets/{preset_id}/apply")
    def apply_llm_preset(preset_id: str, payload: LLMPresetApplyPayload | None = None):
        nonlocal active_llm_provider
        presets = _llm_presets_from_runtime(load_runtime_config(runtime_config_path))
        preset = presets.get(preset_id)
        if preset is None:
            raise HTTPException(status_code=404, detail="preset not found")
        supplied_key = payload.api_key if payload is not None else None
        api_key = supplied_key or preset.get("api_key")
        base_url = str(preset.get("base_url") or "").strip()
        model = str(preset.get("model") or "").strip()
        max_tokens = int(preset.get("max_tokens") or 4096)
        if not base_url or not api_key or not model:
            raise HTTPException(status_code=400, detail="preset requires base_url, api_key, and model before applying")
        active_llm_provider = build_llm_provider_from_config(
            base_url=base_url,
            api_key=str(api_key),
            model=model,
            max_tokens=max_tokens,
        )
        if supplied_key is not None:
            preset = {**preset, "api_key": supplied_key}
            presets[preset_id] = preset
        persisted_config = load_runtime_config(runtime_config_path)
        save_runtime_config(
            runtime_config_path,
            {
                **persisted_config,
                "llm_base_url": base_url,
                "llm_api_key": str(api_key),
                "llm_model": model,
                "llm_max_tokens": max_tokens,
                "llm_active_preset_id": preset_id,
                "llm_presets": presets,
            },
        )
        return {
            "success": True,
            "message": f"已应用 LLM 预设：{preset.get('name') or preset_id}",
            "preset": _public_llm_preset(preset_id, preset),
        }

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
        persisted_config = load_runtime_config(runtime_config_path)
        merged_config = {**active_search_config.model_dump(mode="json"), **payload.model_dump(mode="json")}
        for key_name in (
            "tavily_api_key",
            "serper_api_key",
            "brave_api_key",
            "exa_api_key",
            "firecrawl_api_key",
        ):
            supplied = str(merged_config.get(key_name) or "").strip()
            if supplied:
                merged_config[key_name] = supplied
            else:
                merged_config[key_name] = persisted_config.get(key_name) or getattr(active_search_config, key_name)
        active_search_config = SearchConfig.model_validate(merged_config)
        save_runtime_config(
            runtime_config_path,
            {
                **persisted_config,
                **active_search_config.model_dump(mode="json"),
            },
        )
        active_search_provider = build_search_provider_from_config(
            provider_mode=active_search_config.search_provider_mode,
            tavily_api_key=active_search_config.tavily_api_key,
            tavily_endpoint=active_search_config.tavily_endpoint,
            serper_api_key=active_search_config.serper_api_key,
            serper_endpoint=active_search_config.serper_endpoint,
            brave_api_key=active_search_config.brave_api_key,
            brave_endpoint=active_search_config.brave_endpoint,
            exa_api_key=active_search_config.exa_api_key,
            exa_endpoint=active_search_config.exa_endpoint,
            firecrawl_api_key=active_search_config.firecrawl_api_key,
            firecrawl_search_endpoint=active_search_config.firecrawl_search_endpoint,
        )
        active_content_extraction_provider = build_content_extraction_provider_from_config(
            provider_name=active_search_config.content_extraction_provider,
            firecrawl_api_key=active_search_config.firecrawl_api_key,
            firecrawl_endpoint=active_search_config.firecrawl_endpoint,
            jina_reader_endpoint_prefix=active_search_config.jina_reader_endpoint_prefix,
        )
        status = _build_search_config_status(
            active_search_provider=active_search_provider,
            active_content_extraction_provider=active_content_extraction_provider,
            active_search_config=active_search_config,
        )
        return {
            "success": True,
            "message": "搜索配置已更新",
            "configured": active_search_provider is not None,
            "configured_api_keys": status.configured_api_keys,
        }

    @app.post("/api/config/search/test")
    async def test_search_connection(payload: SearchTestRequest):
        if payload.source_policy == SourcePolicy.USER_MATERIALS_ONLY.value:
            return SearchTestResult(
                success=False,
                message="user_materials_only 禁止联网搜索；请改用项目材料读取/检索测试。",
                source_policy=payload.source_policy,
                providers=[],
            ).model_dump(mode="json")
        if active_search_provider is None:
            return SearchTestResult(
                success=False,
                message="未配置搜索 provider",
                source_policy=payload.source_policy,
                providers=[],
            ).model_dump(mode="json")

        providers = _search_provider_names(active_search_provider)
        effective_allowed_domains: list[str] = []
        effective_blocked_domains: list[str] = []

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
            results = [
                item for item in results
                if item.url and url_matches_domain_policy(
                    item.url,
                    allowed_domains=effective_allowed_domains,
                    blocked_domains=effective_blocked_domains,
                )
            ]
            if not results:
                return SearchTestResult(
                    success=False,
                    message="搜索 Provider 未返回符合域名策略的结果。",
                    source_policy=payload.source_policy,
                    providers=providers,
                    effective_allowed_domains=effective_allowed_domains,
                    effective_blocked_domains=effective_blocked_domains,
                ).model_dump(mode="json")
            extracted_page = None
            extract_target = payload.url_to_extract
            if not extract_target and payload.auto_extract_first_result and results:
                extract_target = results[0].url

            source_assessment = None
            if extract_target:
                page = await active_content_extraction_provider.extract_url(extract_target)
                readable_text = " ".join((page.raw_text or "").split())
                if len(readable_text) < 80 or readable_text.startswith("%PDF-") or "\x00" in readable_text:
                    raise ValueError("抽取结果为空、过短或为不可读二进制内容")
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
                execution_status = _connector_execution_status(
                    connector,
                    active_search_config,
                    search_available=active_search_provider is not None,
                )
                configured = _connector_configured(
                    connector,
                    active_search_config,
                    search_available=active_search_provider is not None,
                )
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
                    execution_status=execution_status,
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
                "先配置 Tavily、Serper、Brave、Exa 或 Firecrawl 任意一个搜索 Key，再载入信源包自检域名约束。"
                if active_search_provider is None
                else "搜索已可用；信源包按钮只做域名过滤自检，不会自动绑定到项目或后续 Agent run。"
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
    embedding_provider=build_embedding_provider(),
    embedding_mode=os.getenv("SECTORBREAKER_EMBEDDING_PROVIDER", "auto"),
)
