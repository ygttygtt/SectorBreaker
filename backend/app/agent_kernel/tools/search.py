"""Search tool for the V3 Agent Kernel."""

from __future__ import annotations

from datetime import UTC, datetime
from math import ceil
from uuid import uuid4

from backend.app.agent_kernel.models import KernelObservation, KernelStateDelta, ToolSpec
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext, ToolRegistry, schema
from backend.app.agent_state.models import (
    KnowledgeClaim,
    KnowledgeLayerId,
    SourceMemory,
    SourceUse,
    TrustLevel,
)
from backend.app.providers.interfaces import SearchQuery
from backend.app.providers.source_policy import search_constraints_for_policy
from backend.app.schemas import (
    ClaimStrength,
    EvidenceItem,
    SourceChannel,
    SourceQuality,
    SourcePolicy,
    VerificationStatus,
)


def register_search_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="search_web",
            description="Search the web for a missing knowledge dimension. Query must be generated from State gaps, not mechanical token splitting.",
            args_schema=schema(
                {
                    "query": {"type": "string"},
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional 2-4 human-style query variants for the same search goal.",
                    },
                    "layer_hint": {"type": "string"},
                    "search_goal": {"type": "string"},
                    "preferred_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional trusted site/domain pack to prioritize for this gap.",
                    },
                    "max_results": {"type": "integer", "default": 8},
                },
                required=["query", "search_goal"],
            ),
        ),
        search_web,
    )


async def search_web(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    if (
        not context.state.autonomy_policy.allow_network_search
        or context.project.source_policy == SourcePolicy.USER_MATERIALS_ONLY
    ):
        return KernelObservation(
            tool_name="search_web",
            success=False,
            summary="搜索被 AutonomyPolicy 或项目 source_policy 阻断。",
            error="network search is not permitted",
            requires_human=True,
        )
    if context.search_provider is None:
        return KernelObservation(
            tool_name="search_web",
            success=False,
            summary="搜索工具不可用：当前没有配置 SearchProvider。",
            error="search provider not configured",
        )
    queries = _query_variants(tool_call.args.get("query"), tool_call.args.get("queries"))
    if not queries:
        return KernelObservation(
            tool_name="search_web",
            success=False,
            summary="搜索工具调用失败：query/queries 为空。",
            error="empty query",
        )
    max_results = int(tool_call.args.get("max_results") or 8)
    layer_id = _layer_from_hint(tool_call.args.get("layer_hint"), context.state.current_layer_id)
    context.search_call_count += 1
    total_result_budget = max(1, min(max_results, 16))
    per_query_limit = max(3, min(8, ceil(total_result_budget / len(queries))))
    allowed_domains, blocked_domains = search_constraints_for_policy(
        {
            "market_scope": context.project.market_scope.value,
            "source_policy": context.project.source_policy.value,
        },
        preferred_domains=[
            str(domain).strip().lower()
            for domain in (tool_call.args.get("preferred_domains") or [])
            if str(domain).strip()
        ],
    )
    results = []
    query_diagnostics = []
    seen_result_urls: set[str] = set()
    for query in queries:
        query_results = await context.search_provider.search(SearchQuery(
            query=query,
            market_scope=context.project.market_scope.value,
            max_results=per_query_limit,
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
        ))
        accepted_for_query = 0
        for result in query_results:
            canonical_url = (result.url or "").strip()
            if canonical_url and canonical_url in seen_result_urls:
                continue
            if canonical_url:
                seen_result_urls.add(canonical_url)
            results.append(result)
            accepted_for_query += 1
            if len(results) >= total_result_budget:
                break
        query_diagnostics.append({
            "query": query,
            "raw_result_count": len(query_results),
            "merged_result_count": accepted_for_query,
        })
        if len(results) >= total_result_budget:
            break
    existing_urls = {item.source_url for item in context.repository.list_evidence(context.project.id) if item.source_url}
    accepted = []
    rejected = 0
    for result in results:
        if result.url and result.url in existing_urls:
            rejected += 1
            continue
        if not result.title and not result.snippet:
            rejected += 1
            continue
        accepted.append(result)
        existing_urls.add(result.url)
    evidence_ids: list[str] = []
    source_memories: list[SourceMemory] = []
    claims: list[KnowledgeClaim] = []
    for result in accepted:
        evidence = EvidenceItem(
            id=f"EV-KERNEL-{context.project.id}-{uuid4().hex[:8]}",
            project_id=context.project.id,
            source_title=result.title or result.url or query,
            snippet=result.snippet or result.title or "",
            source_url=result.url,
            source_type="web",
            source_channel=SourceChannel.SEARCH,
            source_policy=context.project.source_policy.value,
            raw_excerpt=result.snippet,
            summary=result.snippet,
            source_quality=SourceQuality.UNKNOWN,
            claim_strength=ClaimStrength.OPINION,
            collected_by="v3_agent_kernel.search_web",
            confidence=0.45,
            verification_status=VerificationStatus.UNVERIFIED,
        )
        context.repository.add_evidence(evidence)
        evidence_ids.append(evidence.id)
        summary = f"{evidence.source_title}：{evidence.snippet[:260]}"
        memory = SourceMemory(
            source_id=f"search:{evidence.id}",
            source_kind="search",
            title=evidence.source_title,
            url=evidence.source_url,
            summary=summary,
            use=SourceUse.EVIDENCE,
            trust_level=TrustLevel.UNKNOWN,
            evidence_ids=[evidence.id],
            related_layer_ids=[layer_id] if layer_id else [],
            keep_reason=tool_call.reason or str(tool_call.args.get("search_goal") or ""),
            created_at=datetime.now(UTC),
        )
        source_memories.append(memory)
        claims.append(KnowledgeClaim(
            text=f"搜索线索显示：{summary}",
            layer_ids=[layer_id] if layer_id else [],
            evidence_ids=[evidence.id],
            source_memory_ids=[memory.id],
            confidence=0.4,
            trust_level=TrustLevel.UNKNOWN,
            verification_status="unverified",
            needs_verification=True,
            notes="由 Agent Kernel search_web 工具生成的待验证观察。",
        ))
    delta = KernelStateDelta(
        source_memories=source_memories,
        claims=claims,
        evidence_ids=evidence_ids,
        task_notes=[
            f"search_web queries={' | '.join(queries)}; raw={len(results)}; accepted={len(accepted)}; rejected={rejected}"
        ],
    )
    titles = "；".join(result.title for result in accepted[:5])
    query_label = "；".join(queries)
    return KernelObservation(
        tool_name="search_web",
        success=bool(accepted),
        summary=(
            f"Action Observation: 搜索「{query_label}」返回 {len(results)} 条，"
            f"采纳 {len(accepted)} 条，去重/过滤 {rejected} 条。"
            + (f"代表来源：{titles}" if titles else "")
        ),
        data={
            "query": queries[0],
            "queries": queries,
            "query_diagnostics": query_diagnostics,
            "allowed_domains": allowed_domains,
            "blocked_domains": blocked_domains,
            "raw_result_count": len(results),
            "accepted_count": len(accepted),
            "rejected_count": rejected,
            "accepted_titles": [result.title for result in accepted[:8]],
        },
        state_delta=delta,
        evidence_ids=evidence_ids,
    )


def _query_variants(query_value, queries_value) -> list[str]:
    raw_queries = []
    if isinstance(queries_value, list):
        raw_queries.extend(str(item) for item in queries_value)
    raw_query = str(query_value or "").strip()
    if raw_query:
        raw_queries.insert(0, raw_query)
    seen = set()
    queries: list[str] = []
    for item in raw_queries:
        cleaned = " ".join(str(item).split())
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        queries.append(cleaned)
        if len(queries) >= 4:
            break
    return queries


def _layer_from_hint(value, fallback) -> KnowledgeLayerId | None:
    raw = str(value or "").strip()
    if raw:
        try:
            return KnowledgeLayerId(raw)
        except ValueError:
            pass
    return fallback
