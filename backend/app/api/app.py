"""FastAPI app factory."""

from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from backend.app.exporters.markdown import MarkdownExporter
from backend.app.graph.workflow import run_research_workflow
from backend.app.schemas import ResearchProjectCreate
from backend.app.storage.sqlite import SQLiteRepository, init_database


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[str]


def create_app(database_path: Path, export_root: Path) -> FastAPI:
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    exporter = MarkdownExporter(export_root)
    app = FastAPI(title="SectorBreaker")

    @app.post("/api/projects")
    def create_project(payload: ResearchProjectCreate):
        return repository.create_project(payload).model_dump(mode="json")

    @app.get("/api/projects")
    def list_projects():
        return []

    @app.post("/api/projects/{project_id}/runs")
    def run_project(project_id: str):
        project = repository.get_project(project_id)
        state = run_research_workflow(project)
        for evidence in state.evidence:
            repository.add_evidence(evidence)
        for artifact in state.artifacts:
            repository.add_artifact(artifact)
        return state.model_dump(mode="json")

    @app.get("/api/projects/{project_id}/evidence")
    def list_evidence(project_id: str):
        return [item.model_dump(mode="json") for item in repository.list_evidence(project_id)]

    @app.get("/api/projects/{project_id}/artifacts")
    def list_artifacts(project_id: str):
        return [item.model_dump(mode="json") for item in repository.list_artifacts(project_id)]

    @app.post("/api/projects/{project_id}/exports")
    def export_project(project_id: str):
        project = repository.get_project(project_id)
        evidence = repository.list_evidence(project_id)
        artifacts = repository.list_artifacts(project_id)
        return exporter.export_project(project, artifacts, evidence).model_dump(mode="json")

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

    return app
