"""FastAPI app factory."""

import asyncio
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.background import BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.exporters.markdown import MarkdownExporter
from backend.app.graph.workflow import run_research_workflow
from backend.app.providers.factory import build_llm_provider, build_search_provider
from backend.app.providers.interfaces import LLMProvider, SearchProvider
from backend.app.providers.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.schemas import (
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


class LLMTestResult(BaseModel):
    success: bool
    message: str


class UserInputPayload(BaseModel):
    gate: str
    input_type: str  # note | guidance | evidence_data
    content: str


def create_app(
    database_path: Path,
    export_root: Path,
    search_provider: SearchProvider | None = None,
    llm_provider: LLMProvider | None = None,
) -> FastAPI:
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    exporter = MarkdownExporter(export_root)
    active_search_provider = search_provider if search_provider is not None else build_search_provider()
    active_llm_provider = llm_provider if llm_provider is not None else build_llm_provider()
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

    # ── Runs ──────────────────────────────────────────────────────

    @app.post("/api/projects/{project_id}/runs")
    async def run_project(project_id: str, background_tasks: BackgroundTasks):
        """Create a run and start the workflow in the background.

        Returns immediately with the run object so the frontend can
        connect to the SSE endpoint for real-time progress.
        """
        try:
            project = repository.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc

        run = repository.create_run(project_id)
        repository.update_run(run.id, status=RunStatus.RUNNING)

        async def emit_event(event: RunEvent) -> None:
            repository.add_run_event(event, run.id)

        async def run_in_background() -> None:
            try:
                state = await run_research_workflow(
                    project,
                    search_provider=active_search_provider,
                    llm_provider=active_llm_provider,
                    emitter=emit_event,
                )
                for evidence in state.evidence:
                    repository.add_evidence(evidence)
                for artifact in state.artifacts:
                    repository.add_artifact(artifact)
                repository.update_run(run.id, status=RunStatus.COMPLETED, completed_at=datetime.now(UTC))
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
            return repository.get_run(run_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

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

            # If run is already done, close
            if run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
                yield "data: [DONE]\n\n"
                return

            # Poll for new events (simple polling approach)
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

                # Check if run completed
                try:
                    current_run = repository.get_run(run_id)
                    if current_run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
                        # Drain remaining events
                        remaining = repository.list_run_events(run_id, after_id=last_id)
                        for event in remaining:
                            yield f"data: {event.model_dump_json()}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                except KeyError:
                    yield "data: [DONE]\n\n"
                    return

            yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/runs/{run_id}/resume")
    async def resume_run(run_id: str, payload: ResumeRequest):
        """Resume after human review, optionally with supplementary info."""
        try:
            run = repository.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

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

        return {"status": "resumed", "run_id": run_id}

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

    @app.post("/api/config/llm")
    def update_llm_config(payload: LLMConfig):
        nonlocal active_llm_provider
        try:
            active_llm_provider = OpenAICompatibleLLMProvider(
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


app = create_app(
    database_path=Path(os.getenv("SECTORBREAKER_DB_PATH", "data/sectorbreaker.sqlite3")),
    export_root=Path(os.getenv("SECTORBREAKER_EXPORT_ROOT", "exports")),
)
