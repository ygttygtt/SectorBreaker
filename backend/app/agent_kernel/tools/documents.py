"""Document and project-memory tools for the V3 Agent Kernel."""

from __future__ import annotations

import asyncio

from backend.app.agent_kernel.models import KernelObservation, KernelStateDelta, ToolSpec
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext, ToolRegistry, schema
from backend.app.agent_state.models import SourceMemory, SourceUse, TrustLevel
from backend.app.rag import ProjectRetriever


def register_document_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="read_uploaded_report",
            description="Read uploaded external AI reports or user materials before blind web search.",
            args_schema=schema({
                "document_id": {"type": "string"},
                "query": {"type": "string"},
                "max_segments": {"type": "integer", "default": 8},
            }),
        ),
        read_uploaded_report,
    )
    registry.register(
        ToolSpec(
            name="retrieve_project_memory",
            description="Retrieve existing project evidence, uploaded document segments, and generated artifacts relevant to a query.",
            args_schema=schema({"query": {"type": "string"}, "limit": {"type": "integer", "default": 8}}, required=["query"]),
        ),
        retrieve_project_memory,
    )
    registry.register(
        ToolSpec(
            name="inspect_evidence",
            description="Inspect a single evidence record by id.",
            args_schema=schema({"evidence_id": {"type": "string"}}, required=["evidence_id"]),
        ),
        inspect_evidence,
    )


async def read_uploaded_report(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    document_id = str(tool_call.args.get("document_id") or "").strip()
    query = str(tool_call.args.get("query") or "").strip().lower()
    max_segments = int(tool_call.args.get("max_segments") or 8)
    documents = context.repository.list_documents(context.project.id)
    if document_id:
        documents = [item for item in documents if item.id == document_id]
    if query:
        documents = [
            item for item in documents
            if query in item.content.lower()
            or query in (item.file_name or "").lower()
            or query in item.channel.lower()
        ] or documents
    if not documents:
        return KernelObservation(
            tool_name="read_uploaded_report",
            success=False,
            summary="没有找到可读取的上传材料。",
            error="no uploaded documents",
        )
    source_memories: list[SourceMemory] = []
    payload = []
    for document in documents[:4]:
        segments = context.repository.list_document_segments(document.id)[:max_segments]
        segment_text = "\n".join(
            f"[{segment.id}] {segment.heading or 'segment'}: {segment.text[:500]}"
            for segment in segments
        )
        summary = (
            f"{document.file_name or document.id}（channel={document.channel}, chars={document.char_count}, "
            f"citations={document.citation_count}）\n{segment_text[:1800]}"
        )
        source_memories.append(SourceMemory(
            source_id=document.id,
            source_kind=document.channel,
            title=document.file_name or document.id,
            summary=summary[:1200],
            use=SourceUse.CONTEXT,
            trust_level=TrustLevel.LOW if document.channel == "assistant_brief" else TrustLevel.UNKNOWN,
            related_layer_ids=[context.state.current_layer_id] if context.state.current_layer_id else [],
            keep_reason="Agent Kernel 读取上传材料，作为规划、验证和写作上下文。",
        ))
        payload.append({
            "document_id": document.id,
            "file_name": document.file_name,
            "channel": document.channel,
            "segment_count": len(segments),
            "preview": summary,
        })
    return KernelObservation(
        tool_name="read_uploaded_report",
        success=True,
        summary=f"读取上传材料 {len(payload)} 个，已加入 State 作为低/中可信上下文。",
        data={"documents": payload},
        state_delta=KernelStateDelta(source_memories=source_memories),
    )


async def retrieve_project_memory(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    query = str(tool_call.args.get("query") or "").strip()
    limit = int(tool_call.args.get("limit") or 8)
    if not query:
        return KernelObservation(
            tool_name="retrieve_project_memory",
            success=False,
            summary="项目记忆检索失败：query 为空。",
            error="empty query",
        )
    retriever = context.project_retriever or ProjectRetriever(context.repository)
    citations, diagnostics = await asyncio.to_thread(
        retriever.retrieve_with_diagnostics,
        context.project.id,
        query,
        limit,
    )
    snippets = [
        {
            "id": item.source_id,
            "parent_id": item.parent_id,
            "source_type": item.source_type,
            "title": item.title,
            "snippet": item.snippet[:600],
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
    return KernelObservation(
        tool_name="retrieve_project_memory",
        success=bool(snippets),
        summary=f"项目记忆检索「{query}」命中 {len(snippets)} 条。",
        data={
            "query": query,
            "results": snippets[:limit],
            "retrieval": diagnostics.__dict__,
        },
    )


async def inspect_evidence(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    evidence_id = str(tool_call.args.get("evidence_id") or "").strip()
    if not evidence_id:
        return KernelObservation(
            tool_name="inspect_evidence",
            success=False,
            summary="证据检查失败：evidence_id 为空。",
            error="empty evidence_id",
        )
    try:
        evidence = context.repository.get_evidence(evidence_id)
    except KeyError:
        return KernelObservation(
            tool_name="inspect_evidence",
            success=False,
            summary=f"未找到证据：{evidence_id}",
            error="evidence not found",
        )
    return KernelObservation(
        tool_name="inspect_evidence",
        success=True,
        summary=f"证据 {evidence.id}: {evidence.source_title}，质量={evidence.source_quality.value}，验证={evidence.verification_status.value}",
        data=evidence.model_dump(mode="json"),
        evidence_ids=[evidence.id],
    )
