import os
import time
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.agent_state.models import SectorBreakerState
from backend.app.api.app import create_app
from backend.app.providers.fakes import FakeContentExtractionProvider, FakeLLMProvider, FakeSearchProvider
from backend.app.schemas import RunStatus
from backend.app.storage.sqlite import SQLiteRepository


def _docx_bytes(paragraphs: list[str]) -> bytes:
    body = "".join(
        f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>"
        for paragraph in paragraphs
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body>"
        "</w:document>"
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _wait_for_run(client: TestClient, run_id: str, timeout: float = 10.0) -> dict:
    """Poll until the background run completes or fails."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        status = resp.json()["status"]
        if status in ("completed", "failed"):
            return resp.json()
        time.sleep(0.1)
    raise TimeoutError(f"Run {run_id} did not complete within {timeout}s")


def _default_fake_llm():
    """Fake LLM that supports both legacy schemas and Agent Kernel decisions."""

    class KernelAwareFakeLLM(FakeLLMProvider):
        def __init__(self):
            super().__init__(
                response={
                    "domain_definition": "测试行业",
                    "boundaries": "测试边界",
                    "common_confusions": ["测试混淆"],
                    "key_questions": [{"question": "测试问题", "importance": "重要", "source": "搜索", "common_mistake": "无", "priority_1h": "高"}],
                    "data_caliber": [{"metric": "市场规模", "caliber": "统一口径", "confusion": "无", "suitable_for": "概况", "not_suitable_for": "细节", "recommended_source": "行业报告"}],
                    "sections": ["行业定义", "市场现状"],
                    "key_questions_list": ["用户为什么付费？"],
                    "learning_path": ["先学行业定义"],
                    "title": "测试产物",
                    "content": "# 测试内容\n\n行业边界和市场现状分析。",
                }
            )
            self.agent_decision_count = 0

        async def complete_structured(self, messages, response_schema):
            if getattr(response_schema, "__name__", "") == "AgentDecision":
                self.agent_decision_count += 1
                if self.agent_decision_count <= 3:
                    layers = [
                        ("L1_what_why", "L1 本源与需求", "解释领域是什么、为什么存在、解决什么问题。"),
                        ("L2_who", "L2 角色与玩家", "识别用户、供给方、主要玩家和资源角色。"),
                        ("L3_how", "L3 原理与实操", "解释实现机制、工具、流程和关键术语。"),
                    ]
                    layer_id, title, writing_goal = layers[self.agent_decision_count - 1]
                    return response_schema.model_validate({
                        "thought_summary": f"测试环境写作 {title}，验证 Agent Kernel 工具链。",
                        "action_type": "write_artifact",
                        "tool_call": {
                            "tool_name": "write_layer_document",
                            "args": {
                                "layer_id": layer_id,
                                "title": title,
                                "writing_goal": writing_goal,
                                "required_questions": ["是什么？", "为什么重要？", "下一步怎么补库？"],
                            },
                            "reason": "测试环境不依赖外部搜索，先验证真实写作工具。",
                        },
                        "expected_observation": "生成一篇可导出的 Markdown 文档。",
                    })
                return response_schema.model_validate({
                    "thought_summary": "测试产物已经生成，可以结束。",
                    "action_type": "finish",
                    "stop_reason": "测试 Agent Kernel 完成。",
                })
            if response_schema is str:
                return (
                    "# L1 本源与需求\n\n"
                    "## 是什么\n\n"
                    "这是一个用于测试 SectorBreaker V3 Agent Kernel 的结构化知识库文档。它不是空模板，而是验证写作工具能够由 Agent 决策触发。"
                    "本文会保留 Obsidian 友好的结构，例如 [[领域边界]]、[[用户需求]] 和 [[待验证问题]]。"
                    + "测试内容用于模拟详实段落，确保写作工具不会把过薄文本保存为成功产物。"*20
                    + "\n\n"
                    "## 为什么存在\n\n"
                    "用户进入陌生领域时，通常会面对概念、玩家、工具、风险和实践路径混杂的问题。SectorBreaker 的目标是把这些信息放入可持续更新的知识库。"
                    "在真实运行中，本节应引用 evidence id；测试环境中使用 source_evidence_ids 作为证据关联。\n\n"
                    "## 解决什么问题\n\n"
                    "它解决的是从碎片信息到结构化认知的转换问题。文档需要足够详细、可继续补库，并能被 Obsidian 直接打开。"
                    "证据：EV-TEST-1。\n\n"
                    "## 下一步\n\n"
                    "继续补充 L2 角色与玩家、L3 原理与实操、L4 商业与激励、L5 风险与边界。"
                )
            return await super().complete_structured(messages, response_schema)

        async def complete(self, messages):
            return (
                "# L1 本源与需求\n\n"
                "## 是什么\n\n"
                "这是一个用于测试 SectorBreaker V3 Agent Kernel 的结构化知识库文档。它不是空模板，而是验证写作工具能够由 Agent 决策触发。"
                "本文会保留 Obsidian 友好的结构，例如 [[领域边界]]、[[用户需求]] 和 [[待验证问题]]。"
                + "测试内容用于模拟详实段落，确保写作工具不会把过薄文本保存为成功产物。"*20
                + "\n\n"
                "## 为什么存在\n\n"
                "用户进入陌生领域时，通常会面对概念、玩家、工具、风险和实践路径混杂的问题。SectorBreaker 的目标是把这些信息放入可持续更新的知识库。"
                "在真实运行中，本节应引用 evidence id；测试环境中使用 source_evidence_ids 作为证据关联。\n\n"
                "## 解决什么问题\n\n"
                "它解决的是从碎片信息到结构化认知的转换问题。文档需要足够详细、可继续补库，并能被 Obsidian 直接打开。"
                "证据：EV-TEST-1。\n\n"
                "## 下一步\n\n"
                "继续补充 L2 角色与玩家、L3 原理与实操、L4 商业与激励、L5 风险与边界。"
            )

    return KernelAwareFakeLLM()


def _failing_kernel_writer_llm():
    class FailingKernelWriterLLM(FakeLLMProvider):
        def __init__(self):
            super().__init__(response={})
            self.agent_decision_count = 0
            self.writer_calls = 0

        async def complete_structured(self, messages, response_schema):
            if getattr(response_schema, "__name__", "") == "AgentDecision":
                self.agent_decision_count += 1
                return response_schema.model_validate({
                    "thought_summary": "测试写作失败路径：先触发 write_layer_document。",
                    "action_type": "write_artifact",
                    "tool_call": {
                        "tool_name": "write_layer_document",
                        "args": {
                            "layer_id": "L1_what_why",
                            "title": "L1 本源与需求",
                            "writing_goal": "解释领域是什么、为什么存在。",
                            "required_questions": ["是什么？", "为什么存在？"],
                        },
                        "reason": "验证写作失败不能导出模板。",
                    },
                    "expected_observation": "写作工具应失败并阻断。",
                })
            return await super().complete_structured(messages, response_schema)

        async def complete(self, messages):
            self.writer_calls += 1
            raise ValueError("simulated writer failure")

    return FailingKernelWriterLLM()


def _partial_then_failing_kernel_writer_llm():
    class PartialThenFailingKernelWriterLLM(FakeLLMProvider):
        def __init__(self):
            super().__init__(response={})
            self.agent_decision_count = 0
            self.writer_calls = 0

        async def complete_structured(self, messages, response_schema):
            if getattr(response_schema, "__name__", "") == "AgentDecision":
                self.agent_decision_count += 1
                if self.agent_decision_count == 1:
                    return response_schema.model_validate({
                        "thought_summary": "先写第一篇文档。",
                        "action_type": "write_artifact",
                        "tool_call": {
                            "tool_name": "write_layer_document",
                            "args": {
                                "layer_id": "L1_what_why",
                                "title": "L1 本源与需求",
                                "writing_goal": "解释领域是什么、为什么存在。",
                            },
                            "reason": "制造先成功再失败的回归场景。",
                        },
                    })
                return response_schema.model_validate({
                    "thought_summary": "第二篇写作会失败。",
                    "action_type": "write_artifact",
                    "tool_call": {
                        "tool_name": "write_layer_document",
                        "args": {
                            "layer_id": "L2_who",
                            "title": "L2 角色与玩家",
                            "writing_goal": "识别角色与玩家。",
                        },
                        "reason": "验证 failed run 不落库前序半成品。",
                    },
                })
            return await super().complete_structured(messages, response_schema)

        async def complete(self, messages):
            self.writer_calls += 1
            if self.writer_calls == 1:
                return (
                    "# L1 本源与需求\n\n"
                    "## 是什么\n\n"
                    "这是一篇足够长的第一篇文档，用来模拟 Agent Kernel 在第一轮写作中成功生成了一个 artifact。"
                    "它包含 Obsidian 链接 [[领域边界]] 和证据提示 EV-PARTIAL-1。"
                    + "第一篇成功内容。" * 80
                    + "\n\n## 为什么存在\n\n"
                    "这一段继续补充背景，确保 Markdown 通过可用性检查。"
                )
            raise ValueError("second writer failure")

    return PartialThenFailingKernelWriterLLM()


def test_api_runs_research_and_exports_markdown(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    project_response = client.post(
        "/api/projects",
        json={
            "title": "AI Agent Tools",
            "domain": "AI Agent 工具",
            "market_scope": "mixed",
            "depth": "quick",
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    run_response = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"})
    assert run_response.status_code == 200
    run_id = run_response.json()["id"]
    assert run_response.json()["status"] == "running"

    # Wait for the background Agent Kernel to finish.
    run_result = _wait_for_run(client, run_id)
    assert run_result["status"] == "completed"

    artifacts_response = client.get(f"/api/projects/{project_id}/artifacts")
    assert artifacts_response.status_code == 200
    assert len(artifacts_response.json()) >= 3
    artifacts = artifacts_response.json()
    assert {artifact["schema_version"] for artifact in artifacts} == {"v3-knowledge-ops"}
    assert all(not artifact["id"].startswith("ART-V1-") for artifact in artifacts)

    events_text = client.get(f"/api/runs/{run_id}/events").text
    assert "specialist_react_loop" not in events_text
    assert "Knowledge Builder" not in events_text
    assert "Document Writer" not in events_text
    assert "已使用保底" not in events_text
    assert '"gate":"agent_decide"' in events_text
    assert '"gate":"tool_execution"' in events_text
    assert "Observation:" in events_text
    assert "State Update:" in events_text

    export_response = client.post(f"/api/projects/{project_id}/exports")
    assert export_response.status_code == 200
    assert export_response.json()["project_id"] == project_id
    assert Path(export_response.json()["export_dir"]).exists()

    list_response = client.get("/api/projects")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == project_id

    detail_response = client.get(f"/api/projects/{project_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["domain"] == "AI Agent 工具"
    assert detail_response.json()["project_mode"] == "domain_knowledge"


def test_api_follow_up_creates_living_vault_artifact(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    project_response = client.post(
        "/api/projects",
        json={
            "title": "API 中转站",
            "domain": "API 中转站",
            "market_scope": "mixed",
            "depth": "quick",
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    response = client.post(
        f"/api/projects/{project_id}/follow-up",
        json={"question": "反向代理是什么，为什么 API 中转站需要它？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_id"].startswith("ART-FOLLOWUP-")
    assert payload["artifact_path"].startswith("followups/")
    assert payload["updated_artifact_count"] == 1

    artifacts = client.get(f"/api/projects/{project_id}/artifacts").json()
    assert len(artifacts) == 1
    assert artifacts[0]["schema_version"] == "living-vault-followup-v1"
    assert "反向代理" in artifacts[0]["content"]


def test_api_rejects_legacy_events_in_personal_auto_run(tmp_path: Path) -> None:
    class LegacyLeakLLM(FakeLLMProvider):
        async def complete_structured(self, messages, response_schema):
            if getattr(response_schema, "__name__", "") == "AgentDecision":
                return response_schema.model_validate({
                    "thought_summary": "故意触发旧链路标记。",
                    "action_type": "call_tool",
                    "tool_call": {
                        "tool_name": "emit_test_event",
                        "args": {
                            "gate": "specialist_react_loop",
                            "agent": "Document Writer",
                            "message": "Knowledge Builder / Document Writer legacy leak",
                        },
                        "reason": "测试生产守卫必须阻断旧事件。",
                    },
                    "expected_observation": "旧事件应被拒绝。",
                })
            return await super().complete_structured(messages, response_schema)

    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=LegacyLeakLLM(response={}),
        )
    )
    project_response = client.post(
        "/api/projects",
        json={
            "title": "旧链路泄漏测试",
            "domain": "API中转站",
            "market_scope": "mixed",
            "depth": "quick",
        },
    )
    project_id = project_response.json()["id"]

    run_response = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"})
    run_result = _wait_for_run(client, run_response.json()["id"])

    assert run_result["status"] == "failed"
    events_text = client.get(f"/api/runs/{run_response.json()['id']}/events").text
    assert "legacy event blocked" in events_text
    assert "Document Writer" not in events_text
    assert "Knowledge Builder" not in events_text
    assert "specialist_react_loop" not in events_text


def test_api_agent_kernel_writer_failure_marks_run_failed_without_artifacts(tmp_path: Path) -> None:
    llm = _failing_kernel_writer_llm()
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=llm,
        )
    )
    project_response = client.post(
        "/api/projects",
        json={
            "title": "API中转站",
            "domain": "API中转站",
            "market_scope": "mixed",
            "depth": "quick",
        },
    )
    project_id = project_response.json()["id"]

    run_response = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"})
    run_result = _wait_for_run(client, run_response.json()["id"])

    assert run_result["status"] == "failed"
    assert llm.writer_calls >= 3
    artifacts_response = client.get(f"/api/projects/{project_id}/artifacts")
    assert artifacts_response.status_code == 200
    assert artifacts_response.json() == []
    events = client.get(f"/api/runs/{run_response.json()['id']}/events").text
    assert '"gate":"artifact_writing"' in events
    assert '"severity":"error"' in events
    assert "主文档写作失败" in events or "连续写作失败过多" in events


def test_api_agent_kernel_failed_run_keeps_completed_artifacts(tmp_path: Path) -> None:
    llm = _partial_then_failing_kernel_writer_llm()
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=llm,
        )
    )
    project = client.post(
        "/api/projects",
        json={
            "title": "API中转站",
            "domain": "API中转站",
            "market_scope": "mixed",
            "depth": "quick",
        },
    ).json()

    run_response = client.post(f"/api/projects/{project['id']}/runs", params={"auto_run": "true"})
    run_result = _wait_for_run(client, run_response.json()["id"])

    assert run_result["status"] == "failed"
    assert llm.writer_calls >= 4
    artifacts = client.get(f"/api/projects/{project['id']}/artifacts").json()
    assert len(artifacts) == 1
    assert artifacts[0]["title"] == "L1 本源与需求"


def test_api_agent_kernel_uploaded_report_reaches_writer_context(tmp_path: Path) -> None:
    class ReportAwareLLM(FakeLLMProvider):
        def __init__(self):
            super().__init__(response={})
            self.agent_decision_count = 0
            self.writer_prompts: list[str] = []

        async def complete_structured(self, messages, response_schema):
            if getattr(response_schema, "__name__", "") == "AgentDecision":
                self.agent_decision_count += 1
                if self.agent_decision_count == 1:
                    return response_schema.model_validate({
                        "thought_summary": "已经读取上传报告，先写 L1 验证报告是否进入上下文。",
                        "action_type": "write_artifact",
                        "tool_call": {
                            "tool_name": "write_layer_document",
                            "args": {
                                "layer_id": "L1_what_why",
                                "title": "L1 本源与需求",
                                "writing_goal": "基于上传报告解释 API 中转站的本源需求。",
                                "required_questions": ["是什么？", "上传报告说了什么？"],
                            },
                            "reason": "验证外部报告进入 writer context。",
                        },
                        "expected_observation": "生成一篇引用报告信息的文档。",
                    })
                return response_schema.model_validate({
                    "thought_summary": "上传报告已进入文档，可以结束。",
                    "action_type": "finish",
                    "stop_reason": "测试完成。",
                })
            if response_schema is str:
                prompt = messages[-1].content
                self.writer_prompts.append(prompt)
                assert "DeepSearch 报告判断：API 中转站的核心需求来自多模型聚合和成本控制" in prompt
                return (
                    "# L1 本源与需求\n\n"
                    "## 是什么\n\n"
                    "API 中转站是一类把多个模型 API、账号资源或上游接口聚合到统一调用入口的服务。"
                    "根据上传的 DeepSearch 报告判断：API 中转站的核心需求来自多模型聚合和成本控制。"
                    "它面向需要快速接入多家模型、统一账单、切换线路或降低接入复杂度的开发者与团队。"
                    "证据：上传报告。\n\n"
                    "## 为什么存在\n\n"
                    "当模型供应商、价格、可用性、协议和限额不断变化时，单一接口会让使用者承担较高迁移成本。"
                    "中转站通过统一协议、额度管理、路由和聚合能力，把这些变化封装到服务侧。"
                    "这让用户可以更快尝试不同模型，也能把成本、稳定性和接入体验放在同一个操作界面里观察。"
                    "这里的判断仍应标注为低可信上传材料，需要后续搜索验证。\n\n"
                    "## 待验证问题\n\n"
                    "- [[多模型聚合]] 的主流实现方式是什么？\n"
                    "- [[成本控制]] 是否真的是用户付费的首要因素？\n"
                    "- 哪些平台公开说明了额度、路由或协议转换能力？\n"
                    + "补充说明：" * 80
                )
            return await super().complete_structured(messages, response_schema)

        async def complete(self, messages):
            return await self.complete_structured(messages, str)

    llm = ReportAwareLLM()
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=llm,
        )
    )
    project = client.post(
        "/api/projects",
        json={
            "title": "API中转站",
            "domain": "API中转站",
            "market_scope": "mixed",
            "depth": "quick",
        },
    ).json()
    upload = client.post(
        f"/api/projects/{project['id']}/documents",
        json={
            "channel": "assistant_brief",
            "file_name": "deepsearch.md",
            "mime_type": "text/markdown",
            "content": "DeepSearch 报告判断：API 中转站的核心需求来自多模型聚合和成本控制。\n来源：https://example.com/report",
        },
    )
    assert upload.status_code == 200

    run_response = client.post(f"/api/projects/{project['id']}/runs", params={"auto_run": "true"})
    run_result = _wait_for_run(client, run_response.json()["id"])

    run_events = client.get(f"/api/runs/{run_response.json()['id']}/events").text
    assert run_result["status"] == "completed", run_events
    assert llm.writer_prompts
    artifacts = client.get(f"/api/projects/{project['id']}/artifacts").json()
    assert any("多模型聚合和成本控制" in item["content"] for item in artifacts)


def test_api_opens_export_folder_inside_export_root(tmp_path: Path, monkeypatch) -> None:
    opened: list[Path] = []

    def fake_open(path: Path) -> None:
        opened.append(path)

    monkeypatch.setattr("backend.app.api.app._open_local_folder", fake_open)
    export_root = tmp_path / "exports"
    export_dir = export_root / "demo"
    export_dir.mkdir(parents=True)
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=export_root,
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post("/api/exports/open-folder", json={"export_dir": str(export_dir)})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert opened == [export_dir.resolve()]


def test_api_rejects_opening_folder_outside_export_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("backend.app.api.app._open_local_folder", lambda path: None)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post("/api/exports/open-folder", json={"export_dir": str(outside_dir)})

    assert response.status_code == 400


def test_api_project_chat_uses_local_fts(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "Pet Services",
            "domain": "宠物服务",
            "market_scope": "china",
            "depth": "quick",
        },
    ).json()["id"]

    run_resp = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"})
    _wait_for_run(client, run_resp.json()["id"])

    chat_response = client.post(f"/api/projects/{project_id}/chat", json={"question": "应该先学什么"})

    assert chat_response.status_code == 200
    assert chat_response.json()["citations"]
    assert chat_response.json()["citation_details"]


def test_api_chat_uses_uploaded_knowledge_retrieval(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=None,
        )
    )
    project = client.post(
        "/api/projects",
        json={
            "title": "Agent 工程知识库",
            "domain": "AI Agent 工程",
            "market_scope": "china",
            "depth": "quick",
        },
    ).json()
    document = client.post(
        f"/api/projects/{project['id']}/documents",
        json={
            "channel": "user_upload",
            "file_name": "rag-notes.md",
            "mime_type": "text/markdown",
            "content": "RAG 实践通常需要向量数据库、LangGraph 和 Python，并应保留可追溯的来源。",
        },
    )
    assert document.status_code == 200
    run_response = client.post(f"/api/projects/{project['id']}/runs", params={"auto_run": "true"})
    _wait_for_run(client, run_response.json()["id"])

    chat_response = client.post(f"/api/projects/{project['id']}/chat", json={"question": "RAG 实践需要什么"})

    body = chat_response.json()
    assert chat_response.status_code == 200
    assert "RAG" in body["answer"]
    assert body["citations"]
    assert body["citation_details"][0]["source_id"] in body["citations"]

def test_api_exposes_workflow_definition_and_source_policy(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project = client.post(
        "/api/projects",
        json={
            "title": "政策机会",
            "domain": "政策机会",
            "market_scope": "china",
            "depth": "quick",
            "source_policy": "reliable_only",
        },
    ).json()

    assert project["source_policy"] == "reliable_only"

    definition = client.get(f"/api/projects/{project['id']}/workflow-definition")
    assert definition.status_code == 200
    node_ids = {node["id"] for node in definition.json()["nodes"]}
    assert "initialize_state" in node_ids
    assert "agent_decide" in node_ids
    assert "tool_execution" in node_ids
    assert "state_update" in node_ids
    assert "artifact_writing" in node_ids
    assert "knowledge_structuring" not in node_ids
    assert "document_writing" not in node_ids
    assert "specialist_react_loop" not in node_ids


def test_api_persists_and_updates_project_source_preferences(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    created = client.post(
        "/api/projects",
        json={
            "title": "技术信源项目",
            "domain": "AI Agent",
            "market_scope": "mixed",
            "depth": "quick",
            "source_policy": "open_web",
            "source_preferences": {
                "source_pack_ids": ["tech_frontier_pack"],
                "custom_allowed_domains": ["example.com"],
                "blocked_domains": ["spam.example"],
                "enforcement": "require",
            },
        },
    )

    assert created.status_code == 200
    project = created.json()
    assert project["source_preferences"]["source_pack_ids"] == ["tech_frontier_pack"]

    updated = client.patch(
        f"/api/projects/{project['id']}",
        json={
            "source_preferences": {
                "source_pack_ids": ["company_china_pack"],
                "enforcement": "prefer",
            }
        },
    )
    assert updated.status_code == 200
    assert updated.json()["source_preferences"]["source_pack_ids"] == ["company_china_pack"]
    assert client.get(f"/api/projects/{project['id']}").json()["source_preferences"] == updated.json()["source_preferences"]

    rejected = client.post(
        "/api/projects",
        json={
            "title": "未知信源包",
            "domain": "AI",
            "market_scope": "mixed",
            "depth": "quick",
            "source_preferences": {"source_pack_ids": ["not_real"], "enforcement": "prefer"},
        },
    )
    assert rejected.status_code == 422
    assert "unknown source pack" in rejected.json()["detail"]


def test_api_exposes_search_config_status(tmp_path: Path) -> None:
    os.environ.pop("SEARCH_PROVIDER_MODE", None)
    os.environ.pop("TAVILY_API_KEY", None)
    os.environ.pop("SERPER_API_KEY", None)
    os.environ.pop("BRAVE_API_KEY", None)
    os.environ.pop("EXA_API_KEY", None)
    os.environ.pop("CONTENT_EXTRACTION_PROVIDER", None)
    os.environ.pop("FIRECRAWL_API_KEY", None)
    os.environ.pop("JINA_READER_ENDPOINT_PREFIX", None)
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.get("/api/config/search")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is False
    assert payload["provider"] is None
    assert payload["providers"] == []
    assert payload["requested_provider_mode"] == "auto"
    assert payload["extraction_provider"] == "http"
    assert payload["extraction_providers"] == ["http"]
    assert payload["requested_extraction_provider"] == "http"
    assert payload["configured_api_keys"] == []
    assert payload["missing_configuration"] == [
        "tavily_api_key", "serper_api_key", "brave_api_key", "exa_api_key", "firecrawl_api_key",
    ]
    onboarding = {item["key"]: item for item in payload["provider_onboarding"]}
    assert onboarding["firecrawl"]["signup_url"] == "https://www.firecrawl.dev/app/api-keys"
    assert onboarding["firecrawl"]["configured"] is False
    assert onboarding["http"]["configured"] is True
    assert onboarding["http"]["selected"] is True
    assert onboarding["serper"]["pricing_url"] == "https://serper.dev/"

    configured_client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker-configured.sqlite3",
            export_root=tmp_path / "exports-configured",
            search_provider=FakeSearchProvider(results=[]),
            llm_provider=_default_fake_llm(),
        )
    )

    configured_response = configured_client.get("/api/config/search")

    assert configured_response.status_code == 200
    assert configured_response.json()["configured"] is True
    assert configured_response.json()["providers"]
    assert configured_response.json()["extraction_providers"]
    assert "status_message" in configured_response.json()


def test_api_search_status_only_reports_missing_key_for_forced_provider_mode(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "exa",
            "tavily_api_key": "",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "exa-test-key",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "http",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert response.status_code == 200

    status = client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["requested_provider_mode"] == "exa"
    assert status.json()["missing_configuration"] == []


def test_api_search_status_reports_only_selected_provider_missing_key_when_forced_mode_unconfigured(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "exa",
            "tavily_api_key": "tvly-test-key",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "http",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert response.status_code == 200

    status = client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is False
    assert status.json()["requested_provider_mode"] == "exa"
    assert status.json()["missing_configuration"] == ["exa_api_key"]


def test_api_tests_search_and_content_extraction_chain(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            search_provider=FakeSearchProvider(
                results=[
                    {
                        "title": "Official market report",
                        "url": "https://example.org/report",
                        "snippet": "Official statistics and market overview.",
                    }
                ]
            ),
            content_extraction_provider=FakeContentExtractionProvider(
                pages={
                    "https://example.org/report": {
                        "title": "Official Market Report",
                        "raw_text": "Official market report body content with enough readable detail for extraction validation. " * 3,
                        "domain": "example.org",
                    }
                }
            ),
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search/test",
        json={
            "query": "AI agent market",
            "market_scope": "mixed",
            "max_results": 2,
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["result_count"] == 1
    assert response.json()["results"][0]["title"] == "Official market report"
    assert response.json()["extracted_page"]["title"] == "Official Market Report"
    assert response.json()["source_assessment"]["source_quality"] in {"high", "medium", "low", "unknown"}


def test_api_search_test_accepts_domain_filters(tmp_path: Path) -> None:
    captured_queries: list = []

    class CaptureSearchProvider(FakeSearchProvider):
        async def search(self, query):
            captured_queries.append(query)
            return await super().search(query)

    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            search_provider=CaptureSearchProvider(
                results=[
                    {
                        "title": "Official market report",
                        "url": "https://www.sec.gov/report",
                        "snippet": "Official statistics and market overview.",
                    }
                ]
            ),
            content_extraction_provider=FakeContentExtractionProvider(
                pages={
                    "https://www.sec.gov/report": {
                        "title": "Official Market Report",
                        "raw_text": "Official market report body content with enough readable detail for extraction validation. " * 3,
                        "domain": "example.org",
                    }
                }
            ),
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search/test",
        json={
            "query": "AI agent market",
            "market_scope": "mixed",
            "max_results": 2,
            "allowed_domains": ["sec.gov"],
            "blocked_domains": ["medium.com"],
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["source_policy"] == "open_web"
    assert response.json()["effective_allowed_domains"] == ["sec.gov"]
    assert response.json()["effective_blocked_domains"] == ["medium.com"]
    assert captured_queries
    assert captured_queries[0].allowed_domains == ["sec.gov"]
    assert captured_queries[0].blocked_domains == ["medium.com"]


def test_api_search_test_applies_source_policy_constraints(tmp_path: Path) -> None:
    captured_queries: list = []

    class CaptureSearchProvider(FakeSearchProvider):
        async def search(self, query):
            captured_queries.append(query)
            return await super().search(query)

    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            search_provider=CaptureSearchProvider(
                results=[
                    {
                        "title": "Official market report",
                        "url": "https://www.stats.gov.cn/report",
                        "snippet": "Official statistics and market overview.",
                    }
                ]
            ),
            content_extraction_provider=FakeContentExtractionProvider(
                pages={
                    "https://www.stats.gov.cn/report": {
                        "title": "Official Market Report",
                        "raw_text": "Official market report body content with enough readable detail for extraction validation. " * 3,
                        "domain": "example.org",
                    }
                }
            ),
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search/test",
        json={
            "query": "AI agent market",
            "market_scope": "china",
            "source_policy": "reliable_only",
            "max_results": 2,
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["source_policy"] == "reliable_only"
    assert "gov.cn" in response.json()["effective_allowed_domains"]
    assert "medium.com" in response.json()["effective_blocked_domains"]
    assert captured_queries
    assert "gov.cn" in (captured_queries[0].allowed_domains or [])
    assert "medium.com" in (captured_queries[0].blocked_domains or [])


def test_api_updates_search_runtime_config(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "auto",
            "tavily_api_key": "tvly-test-key",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "jina",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True

    status = client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert "tavily" in status.json()["providers"]
    assert status.json()["requested_provider_mode"] == "auto"
    assert "jinareader" in status.json()["extraction_providers"]
    assert status.json()["requested_extraction_provider"] == "jina"
    assert status.json()["configured_api_keys"] == ["tavily"]
    source_status = client.get("/api/config/sources").json()
    connectors = {
        connector["key"]: connector
        for pack in source_status["packs"]
        for connector in pack["connectors"]
    }
    assert connectors["jina_reader_extraction"]["execution_status"] == "ready"
    assert connectors["jina_reader_extraction"]["configured"] is True
    assert connectors["cninfo_public"]["execution_status"] == "available_via_domain_filter"
    assert connectors["cninfo_public"]["configured"] is False


def test_api_search_config_preserves_stored_keys_when_form_submits_blanks(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    client = TestClient(
        create_app(
            database_path=database_path,
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    initial = {
        "search_provider_mode": "tavily",
        "tavily_api_key": "tvly-persisted",
        "content_extraction_provider": "http",
    }
    assert client.post("/api/config/search", json=initial).status_code == 200

    update = client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "tavily",
            "tavily_api_key": "",
            "content_extraction_provider": "jina",
        },
    )

    assert update.status_code == 200
    status = client.get("/api/config/search").json()
    assert status["configured"] is True
    assert status["configured_api_keys"] == ["tavily"]
    runtime_config = (tmp_path / "sectorbreaker.runtime-config.json").read_text(encoding="utf-8")
    assert "tvly-persisted" in runtime_config


def test_api_search_test_blocks_user_materials_only_without_dispatch(tmp_path: Path) -> None:
    provider = FakeSearchProvider(results=[])
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            search_provider=provider,
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search/test",
        json={"query": "must not run", "source_policy": "user_materials_only"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert provider.search_requests == []


def test_api_search_test_does_not_report_empty_results_as_success(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            search_provider=FakeSearchProvider(results=[]),
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post("/api/config/search/test", json={"query": "no results"})

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["result_count"] == 0


def test_api_search_status_reports_firecrawl_fallback_diagnostics(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "auto",
            "tavily_api_key": "tvly-test-key",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "firecrawl",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert response.status_code == 200

    status = client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["requested_extraction_provider"] == "firecrawl"
    assert status.json()["extraction_provider"] == "http"
    assert "firecrawl_api_key" in status.json()["missing_configuration"]
    assert any("Firecrawl" in item for item in status.json()["diagnostics"])


def test_api_updates_search_runtime_config_with_brave_provider(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "brave",
            "tavily_api_key": "",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "brave-test-key",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "http",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True

    status = client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["requested_provider_mode"] == "brave"
    assert "brave" in status.json()["providers"]


def test_api_updates_search_runtime_config_with_explicit_multi_mode(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "multi",
            "tavily_api_key": "tvly-test-key",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "serper-test-key",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "http",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True

    status = client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["requested_provider_mode"] == "multi"
    assert "tavily" in status.json()["providers"]
    assert "serper" in status.json()["providers"]


def test_api_restores_persisted_search_runtime_config_after_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    export_root = tmp_path / "exports"

    first_client = TestClient(
        create_app(
            database_path=database_path,
            export_root=export_root,
            llm_provider=_default_fake_llm(),
        )
    )

    save_response = first_client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "brave",
            "tavily_api_key": "",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "brave-test-key",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "http",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert save_response.status_code == 200

    restarted_client = TestClient(
        create_app(
            database_path=database_path,
            export_root=export_root,
            llm_provider=_default_fake_llm(),
        )
    )

    status = restarted_client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["requested_provider_mode"] == "brave"
    assert "brave" in status.json()["providers"]


def test_api_restores_persisted_llm_runtime_config_after_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    export_root = tmp_path / "exports"

    first_client = TestClient(
        create_app(
            database_path=database_path,
            export_root=export_root,
        )
    )

    save_response = first_client.post(
        "/api/config/llm",
        json={
            "base_url": "https://api.example.com/v1",
            "api_key": "test-key",
            "model": "test-model",
        },
    )

    assert save_response.status_code == 200

    restarted_client = TestClient(
        create_app(
            database_path=database_path,
            export_root=export_root,
        )
    )

    status = restarted_client.get("/api/config/llm")
    assert status.status_code == 200
    assert status.json() == {
        "configured": True,
        "base_url": "https://api.example.com/v1",
        "model": "test-model",
        "max_tokens": 4096,
    }


def test_api_manages_local_llm_presets_without_uploading_to_repo(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    export_root = tmp_path / "exports"
    client = TestClient(create_app(database_path=database_path, export_root=export_root))

    presets_response = client.get("/api/config/llm/presets")
    assert presets_response.status_code == 200
    presets = presets_response.json()["presets"]
    assert {"deepseek-official", "sensenova-v4-flash", "mimo"}.issubset({item["id"] for item in presets})
    assert all("api_key" not in item for item in presets)

    save_response = client.put(
        "/api/config/llm/presets/local-test",
        json={
            "name": "Local Test",
            "base_url": "https://api.local.test/v1",
            "api_key": "local-secret",
            "model": "local-model",
            "max_tokens": 8192,
            "notes": "private preset",
        },
    )
    assert save_response.status_code == 200
    assert save_response.json()["preset"]["has_api_key"] is True
    assert "api_key" not in save_response.json()["preset"]

    apply_response = client.post("/api/config/llm/presets/local-test/apply")
    assert apply_response.status_code == 200

    status = client.get("/api/config/llm")
    assert status.status_code == 200
    assert status.json() == {
        "configured": True,
        "base_url": "https://api.local.test/v1",
        "model": "local-model",
        "max_tokens": 8192,
    }

    restarted = TestClient(create_app(database_path=database_path, export_root=export_root))
    restarted_presets = restarted.get("/api/config/llm/presets").json()["presets"]
    local = next(item for item in restarted_presets if item["id"] == "local-test")
    assert local["has_api_key"] is True
    assert "api_key" not in local


def test_api_restores_persisted_content_extraction_provider_after_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    export_root = tmp_path / "exports"

    first_client = TestClient(
        create_app(
            database_path=database_path,
            export_root=export_root,
            llm_provider=_default_fake_llm(),
        )
    )

    save_response = first_client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "tavily",
            "tavily_api_key": "tvly-test-key",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "jina",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert save_response.status_code == 200

    restarted_client = TestClient(
        create_app(
            database_path=database_path,
            export_root=export_root,
            llm_provider=_default_fake_llm(),
        )
    )

    status = restarted_client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["requested_extraction_provider"] == "jina"
    assert "jinareader" in status.json()["extraction_providers"]


def test_api_search_test_returns_unconfigured_when_search_missing(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search/test",
        json={"query": "AI agent market"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is False


def test_api_updates_search_runtime_config_with_exa_provider(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "exa",
            "tavily_api_key": "",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "exa-test-key",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "http",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True

    status = client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["requested_provider_mode"] == "exa"
    assert "exa" in status.json()["providers"]


def test_api_creates_and_lists_documents(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "AI Reports",
            "domain": "AI 报告",
            "market_scope": "mixed",
            "depth": "quick",
        },
    ).json()["id"]

    created = client.post(
        f"/api/projects/{project_id}/documents",
        json={
            "channel": "assistant_brief",
            "content": "来源：https://www.stats.gov.cn/report\n\n另一来源：https://example.com/blog/best-ai-tools-2026\n\n这是一份调研报告。",
            "file_name": "report.md",
            "mime_type": "text/markdown",
        },
    )

    assert created.status_code == 200
    document_id = created.json()["id"]
    assert created.json()["citation_count"] == 2

    listed = client.get(f"/api/projects/{project_id}/documents")
    fetched = client.get(f"/api/documents/{document_id}")
    segments = client.get(f"/api/documents/{document_id}/segments")
    citations = client.get(f"/api/documents/{document_id}/citations")
    evidence_preview = client.get(f"/api/documents/{document_id}/evidence-preview")
    ingested = client.post(f"/api/documents/{document_id}/ingest-evidence")
    listed_evidence = client.get(f"/api/projects/{project_id}/evidence")

    assert listed.status_code == 200
    assert listed.json()[0]["id"] == document_id
    assert fetched.status_code == 200
    assert fetched.json()["file_name"] == "report.md"
    assert segments.status_code == 200
    assert segments.json()
    assert citations.status_code == 200
    assert citations.json()[0]["source_assessment"]
    assert any(item["source_assessment"]["source_type"] == "government" for item in citations.json())
    assert evidence_preview.status_code == 200
    assert any(item["needs_counterevidence"] is True for item in evidence_preview.json())
    assert any(item["verification_status"] == "partially_verified" for item in evidence_preview.json())
    assert all(item["verification_status"] != "verified" for item in evidence_preview.json())
    assert ingested.status_code == 200
    assert ingested.json()["created_count"] == 2
    assert listed_evidence.status_code == 200
    assert len(listed_evidence.json()) == 2

    ingested_again = client.post(f"/api/documents/{document_id}/ingest-evidence")
    assert ingested_again.status_code == 200
    assert ingested_again.json()["created_count"] == 0


def test_api_uploads_text_document_file(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "Upload Docs",
            "domain": "上传文档",
            "market_scope": "mixed",
            "depth": "quick",
        },
    ).json()["id"]

    response = client.post(
        f"/api/projects/{project_id}/documents/upload",
        data={"channel": "assistant_brief"},
        files={"file": ("brief.md", "# Report\n\n来源：https://example.com/report", "text/markdown")},
    )

    assert response.status_code == 200
    assert response.json()["file_name"] == "brief.md"
    assert response.json()["citation_count"] == 1


def test_api_rejects_unsupported_document_file_type(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "Upload Docs",
            "domain": "上传文档",
            "market_scope": "mixed",
            "depth": "quick",
        },
    ).json()["id"]

    response = client.post(
        f"/api/projects/{project_id}/documents/upload",
        data={"channel": "assistant_brief"},
        files={"file": ("brief.pptx", b"not supported", "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
    )

    assert response.status_code == 400


def test_api_uploads_docx_document_file(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "Upload Word Docs",
            "domain": "上传 Word",
            "market_scope": "mixed",
            "depth": "quick",
        },
    ).json()["id"]

    response = client.post(
        f"/api/projects/{project_id}/documents/upload",
        data={"channel": "assistant_brief"},
        files={
            "file": (
                "brief.docx",
                _docx_bytes(["通义千问 DeepSearch 报告", "来源：https://example.com/qwen-report"]),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["file_name"] == "brief.docx"
    assert "通义千问 DeepSearch 报告" in payload["content"]
    assert payload["citation_count"] == 1


def test_api_exposes_run_snapshot_for_active_run(tmp_path: Path) -> None:
    client = TestClient(create_app(
        database_path=tmp_path / "sectorbreaker.sqlite3",
        export_root=tmp_path / "exports",
        search_provider=FakeSearchProvider(results=[]),
        llm_provider=_default_fake_llm(),
    ))
    project_id = client.post("/api/projects", json={
        "title": "Agent Development",
        "domain": "Agent development",
        "market_scope": "mixed",
        "depth": "quick",
        "source_policy": "open_web",
    }).json()["id"]

    run = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"}).json()
    snapshot = client.get(f"/api/runs/{run['id']}/snapshot")

    assert snapshot.status_code == 200
    payload = snapshot.json()
    assert payload["run_id"] == run["id"]
    assert payload["project_id"] == project_id
    assert payload["status"] in {"collecting", "structuring", "exporting", "completed", "failed"}
    assert "current_stage" in payload
    assert "events" in payload
    assert "artifact_summary" in payload


def test_api_exposes_active_run_for_project_restore(tmp_path: Path) -> None:
    client = TestClient(create_app(
        database_path=tmp_path / "sectorbreaker.sqlite3",
        export_root=tmp_path / "exports",
        search_provider=FakeSearchProvider(results=[]),
        llm_provider=_default_fake_llm(),
    ))
    project_id = client.post("/api/projects", json={
        "title": "Agent Development",
        "domain": "Agent development",
        "market_scope": "mixed",
        "depth": "quick",
        "source_policy": "open_web",
    }).json()["id"]

    run = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"}).json()
    active_run = client.get(f"/api/projects/{project_id}/active-run")

    assert active_run.status_code == 200
    assert active_run.json()["id"] == run["id"]


def test_api_agent_kernel_run_creates_versioned_knowledge_artifacts(tmp_path: Path) -> None:
    search_provider = FakeSearchProvider(results=[{
        "title": "Agent frameworks trend",
        "url": "https://example.com/agent-frameworks",
        "snippet": "Agent frameworks are evolving around tooling, memory, and evaluation.",
    }])
    llm_provider = _default_fake_llm()
    client = TestClient(create_app(
        database_path=tmp_path / "sectorbreaker.sqlite3",
        export_root=tmp_path / "exports",
        search_provider=search_provider,
        llm_provider=llm_provider,
    ))
    project_id = client.post("/api/projects", json={
        "title": "Agent Development",
        "domain": "Agent development",
        "market_scope": "mixed",
        "depth": "quick",
        "source_policy": "open_web",
    }).json()["id"]

    run = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"}).json()
    run_result = _wait_for_run(client, run["id"], timeout=30)
    assert run_result["status"] == "completed"

    artifacts = client.get(f"/api/projects/{project_id}/artifacts").json()
    paths = {item["content_path"] for item in artifacts}
    assert paths == {
        "01-L1 本源与需求.md",
        "02-L2 角色与玩家.md",
        "03-L3 原理与实操.md",
    }
    assert {item["schema_version"] for item in artifacts} == {"v3-knowledge-ops"}
    assert all(item["active"] is True for item in artifacts)
    assert llm_provider.messages


def test_api_run_auto_includes_ingested_document_evidence(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "Document Seed Evidence",
            "domain": "文档证据接入",
            "market_scope": "mixed",
            "depth": "quick",
        },
    ).json()["id"]

    created = client.post(
        f"/api/projects/{project_id}/documents",
        json={
            "channel": "assistant_brief",
            "content": "来源：https://www.stats.gov.cn/report\n\n来源：https://example.com/blog/best-ai-tools-2026",
            "file_name": "report.md",
            "mime_type": "text/markdown",
        },
    )
    document_id = created.json()["id"]
    ingested = client.post(f"/api/documents/{document_id}/ingest-evidence")

    assert ingested.status_code == 200
    assert ingested.json()["created_count"] == 2

    run_response = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"})
    run_result = _wait_for_run(client, run_response.json()["id"])

    assert run_result["status"] == "completed"

    evidence_response = client.get(f"/api/projects/{project_id}/evidence")
    evidence_ids = {item["id"] for item in evidence_response.json()}

    assert "EV-DOC-" in "".join(evidence_ids)
    assert any(item_id.startswith(f"EV-DOC-{document_id}-") for item_id in evidence_ids)

def test_api_run_auto_includes_uploaded_assistant_brief_documents(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "Assistant Brief Auto Include",
            "domain": "外部报告自动接入",
            "market_scope": "mixed",
            "depth": "quick",
        },
    ).json()["id"]

    upload = client.post(
        f"/api/projects/{project_id}/documents/upload",
        data={"channel": "assistant_brief"},
        files={"file": ("brief.md", "# Report\n\n行业判断A\n\n来源：https://example.com/report", "text/markdown")},
    )

    assert upload.status_code == 200

    run_response = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"})
    run_result = _wait_for_run(client, run_response.json()["id"])

    assert run_result["status"] == "completed"

    events_text = client.get(f"/api/runs/{run_response.json()['id']}/events").text
    assert '"gate":"external_materials"' in events_text
    assert "brief.md" in events_text


def test_api_continue_uses_latest_project_checkpoint_after_previous_continue(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    client = TestClient(
        create_app(
            database_path=database_path,
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "Continue Checkpoint",
            "domain": "可持续补库",
            "market_scope": "mixed",
            "depth": "quick",
            "project_mode": "domain_knowledge",
        },
    ).json()["id"]
    repo = SQLiteRepository(database_path)

    first_state = SectorBreakerState.initialize(
        project_id=project_id,
        domain="可持续补库",
        user_goal="build knowledge base",
    )
    first_state.evidence_refs = ["EV-FIRST"]
    repo.save_run_state_checkpoint(
        run_id=project_id,
        project_id=project_id,
        state=first_state,
        checkpoint_type="run_end_completed",
        iteration=4,
    )

    continued_state = SectorBreakerState.initialize(
        project_id=project_id,
        domain="可持续补库",
        user_goal="build knowledge base",
    )
    continued_state.evidence_refs = ["EV-FIRST", "EV-CONTINUED"]
    repo.save_run_state_checkpoint(
        run_id="run-from-previous-continue",
        project_id=project_id,
        state=continued_state,
        checkpoint_type="artifact_write",
        artifact_id="ART-CONTINUED",
        iteration=2,
    )

    response = client.post(f"/api/projects/{project_id}/continue")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "started"
    assert payload["resumed_from_checkpoint"] is True
    events = repo.list_run_events(payload["run_id"])
    assert any(
        "2 evidence refs" in event["message"]
        for event in [event.model_dump(mode="json") for event in events]
        if event["gate"] == "initialize_state"
    )


def test_api_resume_consumes_waiting_run_feedback(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    client = TestClient(
        create_app(
            database_path=database_path,
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={"title": "Resume feedback", "domain": "可恢复研究", "market_scope": "mixed", "depth": "quick"},
    ).json()["id"]
    repo = SQLiteRepository(database_path)
    run = repo.create_run(project_id)
    repo.update_run(run.id, status=RunStatus.WAITING_FOR_HUMAN)
    state = SectorBreakerState.initialize(
        project_id=project_id,
        domain="可恢复研究",
        user_goal="等待用户确认后继续",
    )
    state.run_budget_usage.search_calls = 5
    state.run_budget_usage.provider_requests = 7
    state.run_budget_usage.extraction_requests = 3
    repo.save_run_state_checkpoint(
        run_id=run.id,
        project_id=project_id,
        state=state,
        checkpoint_type="run_end",
        iteration=1,
    )

    response = client.post(
        f"/api/runs/{run.id}/resume",
        json={
            "guidance": "优先解释官方定义",
            "evidence_data": "用户提供的待核验线索",
            "assistant_brief": "外部报告摘要：这个结论仍需交叉验证。",
            "plan_confirmed": True,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "resumed", "run_id": run.id}
    result = _wait_for_run(client, run.id)
    assert result["status"] == "completed"
    events = [event.model_dump(mode="json") for event in repo.list_run_events(run.id)]
    assert any(event["gate"] == "human_feedback" and "消费用户反馈" in event["message"] for event in events)
    checkpoint = repo.load_run_state_checkpoint(run_id=run.id)
    assert checkpoint is not None
    assert any("优先解释官方定义" in item for item in checkpoint.human_feedback)
    assert checkpoint.run_budget_usage.search_calls >= 5
    assert checkpoint.run_budget_usage.provider_requests >= 7
    assert checkpoint.run_budget_usage.extraction_requests >= 3


def test_api_exposes_source_registry_status(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.get("/api/config/sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["packs"]
    pack_names = {pack["name"] for pack in payload["packs"]}
    assert {"company_china_pack", "tech_frontier_pack"}.issubset(pack_names)
    connectors = {
        connector["key"]: connector
        for pack in payload["packs"]
        for connector in pack["connectors"]
    }
    assert connectors["qcc_openapi"]["connector_type"] == "commercial_api"
    assert connectors["qcc_openapi"]["configured"] is False
    assert connectors["gsxt_manual"]["requires_manual_review"] is True
    assert connectors["github_api"]["required_env_keys"] == ["GITHUB_TOKEN"]
    assert connectors["github_api"]["configured"] is False
    assert connectors["github_api"]["execution_status"] == "planned"
    assert connectors["cninfo_public"]["execution_status"] in {
        "needs_search_provider",
        "available_via_domain_filter",
    }
    assert connectors["cninfo_public"]["configured"] is False
