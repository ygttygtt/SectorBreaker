"""Run an end-to-end smoke test against the real local embedding model."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.providers.embeddings import FastEmbedEmbeddingProvider
from backend.app.rag import ProjectRetriever
from backend.app.schemas import (
    MarketScope,
    ProjectDocumentCreate,
    ResearchDepth,
    ResearchProjectCreate,
)
from backend.app.storage.sqlite import SQLiteRepository, init_database


def main() -> None:
    query = "怎样让机器人正确回答公司的规章制度？"
    intended_text = "系统先查阅私有资料，再由语言模型依据检索结果生成回复，能够减少臆测。"
    unrelated_text = "平底锅预热后加入橄榄油，小火烹饪蘑菇并撒上海盐。"

    with TemporaryDirectory(ignore_cleanup_errors=True) as temporary_directory:
        database_path = Path(temporary_directory) / "semantic-smoke.sqlite3"
        init_database(database_path)
        repository = SQLiteRepository(database_path)
        project = repository.create_project(
            ResearchProjectCreate(
                title="真实语义召回验收",
                domain="知识库",
                market_scope=MarketScope.MIXED,
                depth=ResearchDepth.QUICK,
            )
        )
        repository.add_document(
            project.id,
            ProjectDocumentCreate(
                channel="manual",
                file_name="private-knowledge.md",
                mime_type="text/markdown",
                content=intended_text,
            ),
        )
        repository.add_document(
            project.id,
            ProjectDocumentCreate(
                channel="manual",
                file_name="cooking.md",
                mime_type="text/markdown",
                content=unrelated_text,
            ),
        )

        retriever = ProjectRetriever(
            repository,
            FastEmbedEmbeddingProvider(),
            embedding_mode="fastembed",
        )
        hits, diagnostics = retriever.retrieve_with_diagnostics(project.id, query, limit=5)
        result = {
            "query": query,
            "effective_mode": diagnostics.effective_mode,
            "embedding_model": diagnostics.embedding_model,
            "dimension": diagnostics.dimension,
            "index_count": diagnostics.index_count,
            "hits": [
                {
                    "source_id": hit.source_id,
                    "title": hit.title,
                    "retrieval_mode": hit.retrieval_mode,
                    "lexical_rank": hit.lexical_rank,
                    "vector_rank": hit.vector_rank,
                    "vector_score": round(hit.vector_score or 0.0, 4),
                }
                for hit in hits
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))

        assert diagnostics.effective_mode == "hybrid", result
        assert diagnostics.dimension and diagnostics.dimension > 0, result
        assert hits and hits[0].title == "private-knowledge.md", result
        assert len(hits) == 1, result
        assert hits[0].retrieval_mode == "vector", result
        assert hits[0].lexical_rank is None and hits[0].vector_rank == 1, result


if __name__ == "__main__":
    main()
