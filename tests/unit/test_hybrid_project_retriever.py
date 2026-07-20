import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from backend.app.agent_kernel.models import ToolCall
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext
from backend.app.agent_kernel.tools.documents import retrieve_project_memory
from backend.app.agent_state import SectorBreakerState
from backend.app.rag import ProjectRetriever
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    EvidenceItem,
    MarketScope,
    ProjectDocumentCreate,
    ResearchDepth,
    ResearchProjectCreate,
    VerificationStatus,
)
from backend.app.storage.sqlite import SQLiteRepository, init_database


def _repository_with_project(tmp_path: Path) -> tuple[SQLiteRepository, str]:
    database_path = tmp_path / "hybrid-rag.sqlite3"
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    project = repository.create_project(ResearchProjectCreate(
        title="Hybrid RAG acceptance",
        domain="local knowledge management",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
    ))
    return repository, project.id


def _artifact(project_id: str, artifact_id: str, content: str, *, supersedes: str | None = None) -> Artifact:
    return Artifact(
        id=artifact_id,
        project_id=project_id,
        artifact_type=ArtifactType.VAULT_NOTE,
        title=artifact_id,
        content_path="knowledge.md",
        content=content,
        schema_version="v3-knowledge-ops",
        supersedes=supersedes,
    )


def test_semantic_query_recalls_vector_only_source_without_keyword_overlap(
    tmp_path: Path,
    embedding_provider_factory,
) -> None:
    repository, project_id = _repository_with_project(tmp_path)
    repository.add_artifact(_artifact(
        project_id,
        "ART-SEMANTIC-TARGET",
        "外部知识存储能够为生成模型补充企业内部事实。",
    ))
    repository.add_artifact(_artifact(
        project_id,
        "ART-COOKING",
        "番茄炒蛋需要控制火候并在最后加入少量盐。",
    ))
    provider = embedding_provider_factory(
        document_vectors={
            "企业内部事实": (1.0, 0.0, 0.0),
            "番茄炒蛋": (0.0, 1.0, 0.0),
        },
        query_vectors={"answer questions from private company data": (1.0, 0.0, 0.0)},
    )
    retriever = ProjectRetriever(repository, provider, embedding_mode="auto")

    results, diagnostics = retriever.retrieve_with_diagnostics(
        project_id,
        "answer questions from private company data",
    )

    assert [item.source_id for item in results] == ["ART-SEMANTIC-TARGET"]
    assert results[0].retrieval_mode == "vector"
    assert results[0].lexical_rank is None
    assert results[0].vector_rank == 1
    assert results[0].vector_score == pytest.approx(1.0)
    assert diagnostics.effective_mode == "hybrid"
    assert diagnostics.lexical_candidates == 0
    assert diagnostics.vector_candidates == 1


def test_rrf_records_both_lexical_and_vector_provenance(
    tmp_path: Path,
    embedding_provider_factory,
) -> None:
    repository, project_id = _repository_with_project(tmp_path)
    repository.add_artifact(_artifact(
        project_id,
        "ART-HYBRID",
        "shared_anchor describes evidence-aware retrieval.",
    ))
    provider = embedding_provider_factory(
        document_vectors={"shared_anchor": (1.0, 0.0)},
        query_vectors={"shared_anchor": (1.0, 0.0)},
    )
    retriever = ProjectRetriever(repository, provider, embedding_mode="auto", rrf_k=60)

    results = retriever.retrieve(project_id, "shared_anchor")

    hit = next(item for item in results if item.source_id == "ART-HYBRID")
    assert hit.retrieval_mode == "hybrid"
    assert hit.lexical_rank == 1
    assert hit.vector_rank == 1
    assert hit.lexical_score is not None
    assert hit.vector_score == pytest.approx(1.0)
    assert hit.score == pytest.approx((1 / 61) + (1 / 61))
    assert hit.embedding_model == "test-semantic-v1"


def test_incremental_sync_does_not_reembed_unchanged_chunks(
    tmp_path: Path,
    embedding_provider_factory,
) -> None:
    repository, project_id = _repository_with_project(tmp_path)
    repository.add_artifact(_artifact(project_id, "ART-STABLE", "stable semantic source"))
    provider = embedding_provider_factory(
        document_vectors={"stable semantic source": (1.0, 0.0)},
        query_vectors={"semantic question": (1.0, 0.0)},
    )
    retriever = ProjectRetriever(repository, provider, embedding_mode="auto")

    retriever.retrieve(project_id, "semantic question")
    retriever.retrieve(project_id, "semantic question")

    assert provider.document_batches == [["stable semantic source"]]
    assert provider.query_calls == ["semantic question", "semantic question"]
    assert retriever.vector_index is not None
    assert retriever.vector_index.last_sync is not None
    assert retriever.vector_index.last_sync.embedded_chunks == 0
    assert retriever.vector_index.last_sync.unchanged_chunks == 1


def test_rebuild_preserves_retrievable_source_ids(
    tmp_path: Path,
    embedding_provider_factory,
) -> None:
    repository, project_id = _repository_with_project(tmp_path)
    repository.add_artifact(_artifact(project_id, "ART-REBUILD", "rebuildable semantic source"))
    provider = embedding_provider_factory(
        document_vectors={"rebuildable semantic source": (1.0, 0.0)},
        query_vectors={"rebuild question": (1.0, 0.0)},
    )
    retriever = ProjectRetriever(repository, provider, embedding_mode="auto")

    before = [item.source_id for item in retriever.retrieve(project_id, "rebuild question")]
    rebuilt = retriever.rebuild_vector_index(project_id)
    after = [item.source_id for item in retriever.retrieve(project_id, "rebuild question")]

    assert rebuilt.embedded_chunks == 1
    assert rebuilt.index_count == 1
    assert before == after == ["ART-REBUILD"]


def test_failed_force_rebuild_keeps_previous_vector_snapshot(
    tmp_path: Path,
    embedding_provider_factory,
) -> None:
    repository, project_id = _repository_with_project(tmp_path)
    repository.add_artifact(_artifact(project_id, "ART-SAFE-REBUILD", "safe rebuild source"))
    provider = embedding_provider_factory(
        document_vectors={"safe rebuild source": (1.0, 0.0)},
        query_vectors={"safe rebuild question": (1.0, 0.0)},
    )
    retriever = ProjectRetriever(repository, provider, embedding_mode="auto")
    retriever.retrieve(project_id, "safe rebuild question")
    before = repository.list_vector_entries(
        project_id,
        embedding_provider=provider.provider_name,
        embedding_model=provider.model_name,
    )

    provider.fail_documents = True
    with pytest.raises(RuntimeError, match="document embedding failure"):
        retriever.rebuild_vector_index(project_id)
    after = repository.list_vector_entries(
        project_id,
        embedding_provider=provider.provider_name,
        embedding_model=provider.model_name,
    )

    assert after == before
    assert retriever.status(project_id).effective_mode == "lexical_degraded"


def test_metadata_change_updates_citation_without_reembedding_text(
    tmp_path: Path,
    embedding_provider_factory,
) -> None:
    repository, project_id = _repository_with_project(tmp_path)
    evidence = EvidenceItem(
        id="EV-METADATA",
        project_id=project_id,
        source_title="Metadata evidence",
        source_url="https://example.com/metadata",
        snippet="stable evidence body",
        confidence=0.8,
        verification_status=VerificationStatus.VERIFIED,
    )
    repository.add_evidence(evidence)
    provider = embedding_provider_factory(
        document_vectors={"stable evidence body": (1.0, 0.0)},
        query_vectors={"semantic metadata query": (1.0, 0.0)},
    )
    retriever = ProjectRetriever(repository, provider, embedding_mode="auto")
    retriever.retrieve(project_id, "semantic metadata query")

    repository.add_evidence(evidence.model_copy(update={
        "verification_status": VerificationStatus.CONFLICTING,
    }))
    results = retriever.retrieve(project_id, "semantic metadata query")

    assert provider.document_batches == [["Metadata evidence stable evidence body"]]
    assert results[0].verification_status == VerificationStatus.CONFLICTING.value


def test_vector_results_keep_one_best_segment_per_document(
    tmp_path: Path,
    embedding_provider_factory,
) -> None:
    repository, project_id = _repository_with_project(tmp_path)
    document = repository.add_document(project_id, ProjectDocumentCreate(
        channel="manual",
        file_name="long-note.md",
        content="# First\n\nalpha semantic passage.\n\n# Second\n\nbeta semantic passage.",
    ))
    segment_ids = {item.id for item in repository.list_document_segments(document.id)}
    provider = embedding_provider_factory(
        document_vectors={
            "alpha semantic": (1.0, 0.0),
            "beta semantic": (0.9, 0.1),
        },
        query_vectors={"unrelated wording": (1.0, 0.0)},
    )
    retriever = ProjectRetriever(repository, provider, embedding_mode="auto")

    results, diagnostics = retriever.retrieve_with_diagnostics(project_id, "unrelated wording")

    assert diagnostics.vector_candidates == 1
    assert len(results) == 1
    assert results[0].source_id in segment_ids
    assert results[0].parent_id == document.id


def test_empty_project_reindex_stays_pending_until_model_is_loaded(
    tmp_path: Path,
    embedding_provider_factory,
) -> None:
    repository, project_id = _repository_with_project(tmp_path)
    provider = embedding_provider_factory(
        document_vectors={"unused": (1.0, 0.0)},
        query_vectors={"unused": (1.0, 0.0)},
    )
    retriever = ProjectRetriever(repository, provider, embedding_mode="auto")

    result = retriever.rebuild_vector_index(project_id)

    assert result.source_chunks == 0
    assert retriever.status(project_id).effective_mode == "hybrid_pending"


def test_dimension_mismatch_is_reported_as_degraded_instead_of_hybrid(
    tmp_path: Path,
    embedding_provider_factory,
) -> None:
    repository, project_id = _repository_with_project(tmp_path)
    repository.add_artifact(_artifact(project_id, "ART-DIMENSION", "dimension source"))
    provider = embedding_provider_factory(
        document_vectors={"dimension source": (1.0, 0.0)},
        query_vectors={"initial query": (1.0, 0.0)},
    )
    retriever = ProjectRetriever(repository, provider, embedding_mode="auto")
    retriever.retrieve(project_id, "initial query")
    provider.query_vectors["changed shape request"] = (1.0, 0.0, 0.0)
    provider.dimension = 3

    results, diagnostics = retriever.retrieve_with_diagnostics(
        project_id,
        "changed shape request",
    )

    assert results == []
    assert diagnostics.effective_mode == "lexical_degraded"
    assert "dimension mismatch" in (diagnostics.last_error or "")


@pytest.mark.parametrize("mode", ["disabled", " Disabled ", "off", "none"])
def test_disabled_embedding_mode_is_normalized_without_false_degradation(
    tmp_path: Path,
    mode: str,
) -> None:
    repository, project_id = _repository_with_project(tmp_path)
    retriever = ProjectRetriever(repository, embedding_mode=mode)

    _, diagnostics = retriever.retrieve_with_diagnostics(project_id, "anything")

    assert diagnostics.effective_mode == "lexical"
    assert diagnostics.last_error is None


def test_agent_kernel_retrieval_tool_uses_shared_hybrid_retriever(
    tmp_path: Path,
    embedding_provider_factory,
) -> None:
    repository, project_id = _repository_with_project(tmp_path)
    repository.add_artifact(_artifact(project_id, "ART-KERNEL-RAG", "private semantic memory"))
    provider = embedding_provider_factory(
        document_vectors={"private semantic memory": (1.0, 0.0)},
        query_vectors={"different agent wording": (1.0, 0.0)},
    )
    retriever = ProjectRetriever(repository, provider, embedding_mode="auto")

    async def emit(_event) -> None:
        return None

    context = KernelRuntimeContext(
        project=repository.get_project(project_id),
        repository=repository,
        state=SectorBreakerState.initialize(
            project_id=project_id,
            domain="local knowledge management",
            user_goal="maintain knowledge",
        ),
        search_provider=None,
        llm_provider=None,
        emit_event=emit,
        project_retriever=retriever,
    )
    observation = asyncio.run(retrieve_project_memory(
        ToolCall(
            tool_name="retrieve_project_memory",
            args={"query": "different agent wording", "limit": 3},
            reason="Use project-local memory.",
        ),
        context,
    ))

    assert observation.success is True
    assert observation.data["retrieval"]["effective_mode"] == "hybrid"
    assert observation.data["results"][0]["id"] == "ART-KERNEL-RAG"
    assert observation.data["results"][0]["retrieval_mode"] == "vector"


def test_concurrent_project_sync_embeds_unchanged_snapshot_once(
    tmp_path: Path,
    embedding_provider_factory,
) -> None:
    repository, project_id = _repository_with_project(tmp_path)
    repository.add_artifact(_artifact(project_id, "ART-CONCURRENT", "concurrent semantic source"))
    provider = embedding_provider_factory(
        document_vectors={"concurrent semantic source": (1.0, 0.0)},
        query_vectors={"parallel question": (1.0, 0.0)},
    )
    retriever = ProjectRetriever(repository, provider, embedding_mode="auto")
    first_embedding_started = threading.Event()
    release_first_embedding = threading.Event()
    original_embed_documents = provider.embed_documents

    def blocked_embed_documents(texts: list[str]) -> list[list[float]]:
        first_embedding_started.set()
        assert release_first_embedding.wait(timeout=2)
        return original_embed_documents(texts)

    provider.embed_documents = blocked_embed_documents
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(retriever.retrieve, project_id, "parallel question")
        assert first_embedding_started.wait(timeout=2)
        second = executor.submit(retriever.retrieve, project_id, "parallel question")
        release_first_embedding.set()
        first.result(timeout=5)
        second.result(timeout=5)

    assert provider.document_batches == [["concurrent semantic source"]]


def test_changed_content_is_reembedded_and_superseded_revision_is_removed(
    tmp_path: Path,
    embedding_provider_factory,
) -> None:
    repository, project_id = _repository_with_project(tmp_path)
    repository.add_artifact(_artifact(project_id, "ART-REV-1", "first revision content"))
    provider = embedding_provider_factory(
        document_vectors={
            "first revision": (1.0, 0.0, 0.0),
            "changed content": (0.0, 1.0, 0.0),
            "active successor": (0.0, 0.0, 1.0),
        },
        query_vectors={
            "first query": (1.0, 0.0, 0.0),
            "changed query": (0.0, 1.0, 0.0),
            "successor query": (0.0, 0.0, 1.0),
        },
    )
    retriever = ProjectRetriever(repository, provider, embedding_mode="auto")
    retriever.retrieve(project_id, "first query")

    repository.add_artifact(_artifact(project_id, "ART-REV-1", "changed content with same source id"))
    changed_results = retriever.retrieve(project_id, "changed query")

    assert changed_results[0].source_id == "ART-REV-1"
    assert provider.document_batches[-1] == ["changed content with same source id"]

    repository.add_artifact(_artifact(
        project_id,
        "ART-REV-2",
        "active successor knowledge",
        supersedes="ART-REV-1",
    ))
    successor_results = retriever.retrieve(project_id, "successor query")
    entries = repository.list_vector_entries(
        project_id,
        embedding_provider=provider.provider_name,
        embedding_model=provider.model_name,
    )

    assert successor_results[0].source_id == "ART-REV-2"
    assert {entry.source_id for entry in entries} == {"ART-REV-2"}
    assert retriever.vector_index is not None
    assert retriever.vector_index.last_sync is not None
    assert retriever.vector_index.last_sync.deleted_chunks == 1
    assert provider.document_batches == [
        ["first revision content"],
        ["changed content with same source id"],
        ["active successor knowledge"],
    ]


def test_provider_failure_is_reported_as_explicit_lexical_degraded_mode(
    tmp_path: Path,
    embedding_provider_factory,
) -> None:
    repository, project_id = _repository_with_project(tmp_path)
    repository.add_artifact(_artifact(project_id, "ART-LEXICAL", "degraded_anchor remains searchable"))
    provider = embedding_provider_factory(
        document_vectors={"degraded_anchor": (1.0, 0.0)},
        query_vectors={"degraded_anchor": (1.0, 0.0)},
        fail_query=True,
    )
    retriever = ProjectRetriever(repository, provider, embedding_mode="auto")

    results, diagnostics = retriever.retrieve_with_diagnostics(project_id, "degraded_anchor")

    assert [item.source_id for item in results] == ["ART-LEXICAL"]
    assert results[0].retrieval_mode == "lexical"
    assert diagnostics.effective_mode == "lexical_degraded"
    assert diagnostics.vector_candidates == 0
    assert diagnostics.last_error == "RuntimeError: deterministic query embedding failure"
