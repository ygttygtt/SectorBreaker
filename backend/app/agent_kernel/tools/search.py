"""Search tool for the V3 Agent Kernel."""

from __future__ import annotations

from dataclasses import asdict
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
from backend.app.providers.search_execution import execute_search
from backend.app.providers.source_policy import build_project_search_constraints, url_matches_domain_policy
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
    if context.provider_request_count >= context.max_provider_requests:
        return KernelObservation(
            tool_name="search_web",
            success=False,
            summary=f"Provider 请求预算已用尽（{context.max_provider_requests} 次），需要调整计划或请求用户授权。",
            error="provider request budget exhausted",
            requires_human=True,
            data={
                "run_provider_request_count": context.provider_request_count,
                "max_provider_requests": context.max_provider_requests,
            },
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
    context.consume_search_call()
    total_result_budget = max(1, min(max_results, 16))
    per_query_limit = max(3, min(8, ceil(total_result_budget / len(queries))))
    constraints = build_project_search_constraints(
        {
            "market_scope": context.project.market_scope.value,
            "source_policy": context.project.source_policy.value,
            "source_preferences": {
                "source_pack_ids": context.state.meta_context.source_pack_ids,
                "custom_allowed_domains": context.state.meta_context.custom_allowed_domains,
                "blocked_domains": context.state.meta_context.blocked_domains,
                "enforcement": context.state.meta_context.source_enforcement,
            },
        },
        preferred_domains=[
            str(domain).strip().lower()
            for domain in (tool_call.args.get("preferred_domains") or [])
            if str(domain).strip()
        ],
    )
    allowed_domains = constraints.primary_allowed_domains
    blocked_domains = constraints.blocked_domains
    results = []
    query_diagnostics = []
    seen_result_urls: set[str] = set()
    result_queries: dict[str, str] = {}
    domain_rejected = 0
    provider_request_count = 0
    provider_outcomes = []
    result_provenance: dict[str, dict] = {}
    search_attempt_id = f"search-{uuid4().hex}"
    fallback_used = False
    for query in queries:
        primary_response = await execute_search(
            context.search_provider,
            SearchQuery(
                query=query,
                market_scope=context.project.market_scope.value,
                max_results=per_query_limit,
                allowed_domains=constraints.primary_allowed_domains,
                blocked_domains=constraints.blocked_domains,
            ),
            request_budget=max(0, context.max_provider_requests - context.provider_request_count),
        )
        primary_results = primary_response.results
        provider_request_count += primary_response.request_count
        context.consume_provider_requests(primary_response.request_count)
        provider_outcomes.extend(asdict(item) for item in primary_response.provider_outcomes)
        batches = [(primary_results, constraints.primary_allowed_domains, "preferred")]
        fallback_results = []
        fallback_reason = None
        if (
            constraints.fallback_allowed_domains is not None
            and len(primary_results) < min(2, per_query_limit)
            and constraints.fallback_allowed_domains != constraints.primary_allowed_domains
        ):
            fallback_reason = "preferred_sources_returned_insufficient_results"
            fallback_response = await execute_search(
                context.search_provider,
                SearchQuery(
                    query=query,
                    market_scope=context.project.market_scope.value,
                    max_results=per_query_limit,
                    allowed_domains=constraints.fallback_allowed_domains,
                    blocked_domains=constraints.blocked_domains,
                ),
                request_budget=max(0, context.max_provider_requests - context.provider_request_count),
            )
            fallback_results = fallback_response.results
            provider_request_count += fallback_response.request_count
            context.consume_provider_requests(fallback_response.request_count)
            provider_outcomes.extend(asdict(item) for item in fallback_response.provider_outcomes)
            fallback_used = True
            batches.append((fallback_results, constraints.fallback_allowed_domains, "fallback"))
        accepted_for_query = 0
        for batch_results, batch_allowed_domains, batch_kind in batches:
            for result in batch_results:
                canonical_url = (result.url or "").strip()
                if not canonical_url or not url_matches_domain_policy(
                    canonical_url,
                    allowed_domains=batch_allowed_domains,
                    blocked_domains=blocked_domains,
                ):
                    domain_rejected += 1
                    continue
                if canonical_url in seen_result_urls:
                    continue
                seen_result_urls.add(canonical_url)
                result_queries[canonical_url] = query
                result_provenance[canonical_url] = {
                    "search_attempt_id": search_attempt_id,
                    "query": query,
                    "phase": batch_kind,
                    "provider_id": str((result.provider_metadata or {}).get("provider") or "unknown"),
                    "effective_allowed_domains": batch_allowed_domains,
                    "effective_blocked_domains": blocked_domains,
                    "fallback_used": batch_kind == "fallback",
                }
                results.append(result)
                accepted_for_query += 1
                if len(results) >= total_result_budget:
                    break
            if len(results) >= total_result_budget:
                break
        query_diagnostics.append({
            "query": query,
            "raw_result_count": len(primary_results) + len(fallback_results),
            "preferred_result_count": len(primary_results),
            "fallback_result_count": len(fallback_results),
            "fallback_reason": fallback_reason,
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
    extraction_diagnostics: list[dict[str, str | bool]] = []
    for index, result in enumerate(accepted):
        result_url = (result.url or "").strip()
        raw_excerpt = result.snippet or result.title or ""
        source_title = result.title or result.url or query
        extraction_provider = None
        extraction_metadata = {}
        extracted_at = None
        assessment = None
        if index < 3 and result.url and context.content_extraction_provider is not None:
            if context.extraction_request_count >= context.max_extraction_requests:
                extraction_diagnostics.append({
                    "url": result.url,
                    "success": False,
                    "error": "skipped_budget",
                })
            else:
                context.consume_extraction_request()
                try:
                    page = await context.content_extraction_provider.extract_url(result.url)
                    extracted_text = _readable_extracted_text(page.raw_text)
                    if extracted_text:
                        raw_excerpt = extracted_text[:12000]
                        source_title = page.title or source_title
                        extraction_provider = page.extraction_provider or type(context.content_extraction_provider).__name__
                        extraction_metadata = dict(page.extraction_metadata or {})
                        extracted_at = datetime.now(UTC)
                        extraction_diagnostics.append({
                            "url": result.url,
                            "success": True,
                            "provider": extraction_provider,
                        })
                    else:
                        extraction_diagnostics.append({
                            "url": result.url,
                            "success": False,
                            "error": "empty_or_unreadable_content",
                        })
                except Exception as exc:
                    extraction_diagnostics.append({
                        "url": result.url,
                        "success": False,
                        "error": f"{type(exc).__name__}: {str(exc)[:160]}",
                    })
        if context.source_verification_provider is not None:
            try:
                assessment = await context.source_verification_provider.assess_source(
                    url=result.url,
                    title=source_title,
                    snippet=result.snippet,
                    extracted_text=raw_excerpt if extraction_provider else None,
                    source_policy=context.project.source_policy.value,
                )
            except Exception as exc:
                extraction_diagnostics.append({
                    "url": result.url,
                    "success": False,
                    "error": f"source_assessment:{type(exc).__name__}: {str(exc)[:120]}",
                })
        source_quality = _source_quality(assessment.source_quality if assessment else None)
        verification_status = _verification_status(
            assessment.recommended_verification_status if assessment else None
        )
        evidence = EvidenceItem(
            id=f"EV-KERNEL-{context.project.id}-{uuid4().hex[:8]}",
            project_id=context.project.id,
            source_title=source_title,
            snippet=result.snippet or result.title or "",
            source_url=result.url,
            source_type=assessment.source_type if assessment else "web",
            source_channel=SourceChannel.SEARCH,
            source_policy=context.project.source_policy.value,
            raw_excerpt=raw_excerpt,
            summary=raw_excerpt[:800],
            extraction_provider=extraction_provider,
            extraction_metadata=extraction_metadata,
            collection_metadata={
                **result_provenance.get(result_url, {
                    "search_attempt_id": search_attempt_id,
                    "query": result_queries.get(result_url, queries[0]),
                    "phase": "preferred",
                    "provider_id": str((result.provider_metadata or {}).get("provider") or "unknown"),
                    "effective_allowed_domains": allowed_domains,
                    "effective_blocked_domains": blocked_domains,
                    "fallback_used": False,
                }),
                "source_pack_ids": constraints.source_pack_ids,
                "source_enforcement": constraints.enforcement,
            },
            extracted_at=extracted_at,
            source_quality=source_quality,
            claim_strength=ClaimStrength.OPINION,
            bias_risk=assessment.reliability_notes if assessment else None,
            needs_counterevidence=True,
            collected_by="v3_agent_kernel.search_web_extract_assess",
            confidence=0.6 if source_quality == SourceQuality.HIGH else 0.45,
            verification_status=verification_status,
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
            trust_level=_trust_level(source_quality),
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
            trust_level=_trust_level(source_quality),
            verification_status=verification_status.value,
            needs_verification=True,
            notes="由 Agent Kernel search_web 工具生成；来源评级不等于 claim 已核验。",
        ))
    delta = KernelStateDelta(
        source_memories=source_memories,
        claims=claims,
        evidence_ids=evidence_ids,
        task_notes=[
            f"search_web queries={' | '.join(queries)}; raw={len(results)}; accepted={len(accepted)}; "
            f"rejected={rejected}; rejected_by_domain={domain_rejected}; extracted="
            f"{sum(1 for item in extraction_diagnostics if item.get('success'))}"
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
            "source_pack_ids": constraints.source_pack_ids,
            "source_enforcement": constraints.enforcement,
            "fallback_used": fallback_used,
            "provider_request_count": provider_request_count,
            "provider_outcomes": provider_outcomes,
            "run_provider_request_count": context.provider_request_count,
            "run_extraction_request_count": context.extraction_request_count,
            "raw_result_count": len(results),
            "accepted_count": len(accepted),
            "rejected_count": rejected,
            "rejected_by_domain": domain_rejected,
            "extraction_diagnostics": extraction_diagnostics,
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


def _readable_extracted_text(value: str | None) -> str | None:
    text = " ".join(str(value or "").split())
    if len(text) < 80 or text.startswith("%PDF-") or "\x00" in text:
        return None
    return text


def _source_quality(value: str | None) -> SourceQuality:
    try:
        return SourceQuality(value or SourceQuality.UNKNOWN.value)
    except ValueError:
        return SourceQuality.UNKNOWN


def _verification_status(value: str | None) -> VerificationStatus:
    try:
        status = VerificationStatus(value or VerificationStatus.UNVERIFIED.value)
    except ValueError:
        return VerificationStatus.UNVERIFIED
    return min(status, VerificationStatus.PARTIALLY_VERIFIED, key=_verification_rank)


def _verification_rank(status: VerificationStatus) -> int:
    return {
        VerificationStatus.UNVERIFIED: 0,
        VerificationStatus.CONFLICTING: 0,
        VerificationStatus.PARTIALLY_VERIFIED: 1,
        VerificationStatus.VERIFIED: 2,
    }[status]


def _trust_level(source_quality: SourceQuality) -> TrustLevel:
    if source_quality == SourceQuality.HIGH:
        return TrustLevel.HIGH
    if source_quality == SourceQuality.MEDIUM:
        return TrustLevel.MEDIUM
    if source_quality == SourceQuality.LOW:
        return TrustLevel.LOW
    return TrustLevel.UNKNOWN
