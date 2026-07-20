from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.app import create_app


def test_retrieval_status_reindex_and_chat_return_hybrid_provenance(
    tmp_path: Path,
    embedding_provider_factory,
) -> None:
    provider = embedding_provider_factory(
        document_vectors={"private_memory_anchor": (1.0, 0.0, 0.0)},
        query_vectors={"private_memory_anchor": (1.0, 0.0, 0.0)},
    )
    client = TestClient(create_app(
        database_path=tmp_path / "hybrid-api.sqlite3",
        export_root=tmp_path / "exports",
        embedding_provider=provider,
        embedding_mode="auto",
    ))
    project_id = client.post("/api/projects", json={
        "title": "Hybrid API",
        "domain": "semantic retrieval",
        "market_scope": "mixed",
        "depth": "quick",
    }).json()["id"]
    document = client.post(f"/api/projects/{project_id}/documents", json={
        "channel": "user_upload",
        "file_name": "memory.md",
        "content": "# Memory\n\nprivate_memory_anchor supplies grounded internal facts.",
    }).json()
    segments = client.get(f"/api/documents/{document['id']}/segments").json()
    segment_id = next(item["id"] for item in segments if "private_memory_anchor" in item["text"])

    pending = client.get("/api/config/retrieval", params={"project_id": project_id})
    assert pending.status_code == 200
    pending_payload = pending.json()
    assert pending_payload["effective_mode"] == "hybrid_pending"
    assert pending_payload["embedding_provider"] == "deterministic-local"
    assert pending_payload["embedding_model"] == "test-semantic-v1"
    assert pending_payload["embedding_configured"] is True
    assert pending_payload["embedding_available"] is True
    assert pending_payload["embedding_loaded"] is False
    assert pending_payload["dimension"] is None
    assert pending_payload["index_count"] == 0
    assert pending_payload["last_error"] is None

    reindex = client.post(f"/api/projects/{project_id}/retrieval/reindex")
    assert reindex.status_code == 200
    assert reindex.json()["source_chunks"] == len(segments)
    assert reindex.json()["embedded_chunks"] == len(segments)
    assert reindex.json()["index_count"] == len(segments)
    assert reindex.json()["embedding_provider"] == "deterministic-local"
    assert reindex.json()["embedding_model"] == "test-semantic-v1"

    ready = client.get("/api/config/retrieval", params={"project_id": project_id})
    assert ready.status_code == 200
    assert ready.json()["effective_mode"] == "hybrid"
    assert ready.json()["dimension"] == 3
    assert ready.json()["index_count"] == len(segments)

    chat = client.post(
        f"/api/projects/{project_id}/chat",
        json={"question": "private_memory_anchor"},
    )
    assert chat.status_code == 200
    payload = chat.json()
    assert payload["retrieval_mode"] == "hybrid"
    assert payload["embedding_model"] == "test-semantic-v1"
    assert payload["retrieval_diagnostics"]["effective_mode"] == "hybrid"
    assert payload["retrieval_diagnostics"]["vector_candidates"] == 1
    detail = next(item for item in payload["citation_details"] if item["source_id"] == segment_id)
    assert detail["retrieval_mode"] == "hybrid"
    assert detail["lexical_rank"] is not None
    assert detail["vector_rank"] == 1
    assert detail["lexical_score"] is not None
    assert detail["vector_score"] == 1.0
    assert detail["embedding_model"] == "test-semantic-v1"


def test_chat_reports_lexical_degraded_when_embedding_query_fails(
    tmp_path: Path,
    embedding_provider_factory,
) -> None:
    provider = embedding_provider_factory(
        document_vectors={"failure_anchor": (1.0, 0.0)},
        query_vectors={"failure_anchor": (1.0, 0.0)},
        fail_query=True,
    )
    client = TestClient(create_app(
        database_path=tmp_path / "degraded-api.sqlite3",
        export_root=tmp_path / "exports",
        embedding_provider=provider,
        embedding_mode="auto",
    ))
    project_id = client.post("/api/projects", json={
        "title": "Degraded API",
        "domain": "fallback retrieval",
        "market_scope": "mixed",
        "depth": "quick",
    }).json()["id"]
    client.post(f"/api/projects/{project_id}/documents", json={
        "channel": "user_upload",
        "file_name": "fallback.md",
        "content": "failure_anchor must remain available through lexical retrieval.",
    })

    chat = client.post(
        f"/api/projects/{project_id}/chat",
        json={"question": "failure_anchor"},
    )

    assert chat.status_code == 200
    payload = chat.json()
    assert payload["retrieval_mode"] == "lexical_degraded"
    assert payload["retrieval_diagnostics"]["last_error"] == (
        "RuntimeError: deterministic query embedding failure"
    )
    assert payload["citation_details"]
    assert all(item["retrieval_mode"] == "lexical" for item in payload["citation_details"])

    status = client.get("/api/config/retrieval", params={"project_id": project_id})
    assert status.status_code == 200
    assert status.json()["effective_mode"] == "lexical_degraded"
    assert "deterministic query embedding failure" in status.json()["last_error"]
