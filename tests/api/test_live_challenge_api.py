import re

from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.providers.fakes import FakeContentExtractionProvider
from backend.app.providers.interfaces import SearchResult
from backend.app.schemas import (
    ClaimCheck,
    ClaimCheckStatus,
    DeliverableFinding,
)


class ChallengeLLM:
    async def complete_structured(self, messages, response_schema):
        name = response_schema.__name__
        prompt = messages[-1].content
        if name == "MissionPlanDraft":
            return response_schema.model_validate({
                "objective": "形成量子传感的证据型入门地图",
                "planning_reason": "基础与生态并行，随后反证验收和编辑。",
                "tasks": [
                    {
                        "key": "foundations",
                        "task_type": "research",
                        "objective": "研究定义、核心概念与运行机制",
                        "research_angle": "科学基础",
                        "required_capabilities": ["research_foundations"],
                        "acceptance_criteria": ["至少一条真实证据"],
                    },
                    {
                        "key": "ecosystem",
                        "task_type": "research",
                        "objective": "研究参与者、应用和产业关系",
                        "research_angle": "产业生态",
                        "required_capabilities": ["research_ecosystem"],
                        "acceptance_criteria": ["至少一条真实证据"],
                    },
                    {
                        "key": "verify",
                        "task_type": "verify",
                        "objective": "核查核心结论与重要争议",
                        "research_angle": "反证与边界",
                        "required_capabilities": ["verify_claims", "counterevidence"],
                        "depends_on": ["foundations", "ecosystem"],
                        "acceptance_criteria": ["至少一个 ClaimCheck"],
                    },
                    {
                        "key": "edit",
                        "task_type": "edit",
                        "objective": "合并已验收交付形成 Starter Note",
                        "research_angle": "知识编辑",
                        "required_capabilities": ["synthesize_starter_note", "propose_change_set"],
                        "depends_on": ["verify"],
                        "acceptance_criteria": ["七个章节并引用至少两个 Evidence ID"],
                    },
                ],
            })
        if name == "ResearchDecision":
            ecosystem = "产业生态" in prompt or "参与者、应用" in prompt
            return response_schema(
                query="quantum sensing industry applications" if ecosystem else "quantum sensing review mechanisms",
                queries=[],
                search_goal="寻找权威定义、机制、应用与限制",
                rationale="直接覆盖任务缺口",
            )
        evidence_ids = list(dict.fromkeys(re.findall(r"EV-KERNEL-[A-Za-z0-9_-]+", prompt)))
        if name == "ResearchSynthesis":
            return response_schema(
                summary="基于真实正文整理了定义、机制或生态。",
                findings=[DeliverableFinding(
                    summary="量子传感利用可控量子态对外部物理量变化的响应进行测量。",
                    evidence_ids=evidence_ids[:2],
                    confidence=0.8,
                )],
                unresolved_questions=["不同应用场景的工程收益如何比较？"],
            )
        if name == "VerificationSynthesis":
            return response_schema(
                summary="已检查证据支持范围并保留工程化不确定性。",
                claim_checks=[ClaimCheck(
                    claim="量子传感在所有场景都必然优于经典传感",
                    status=ClaimCheckStatus.CONFLICTING,
                    evidence_ids=evidence_ids[:2],
                    reason="证据只支持特定测量条件，不能外推到所有工程场景。",
                )],
                unresolved_questions=["实验灵敏度如何转化为系统级优势？"],
            )
        if name == "_DemoLLMProbe":
            return response_schema(ok=True)
        raise AssertionError(name)

    async def complete(self, messages):
        ids = list(dict.fromkeys(re.findall(r"EV-KERNEL-[A-Za-z0-9_-]+", messages[-1].content)))
        assert len(ids) >= 2
        sections = [
            "领域定义与边界",
            "核心概念",
            "关键参与者",
            "运行机制",
            "争议与不确定性",
            "后续研究问题",
            "来源",
        ]
        paragraphs = []
        for index, section in enumerate(sections):
            evidence_id = ids[index % 2]
            paragraphs.append(
                f"## {section}\n\n"
                + ("本节基于已验收证据说明量子传感的研究边界、概念联系、系统条件与可验证限制。"
                   "现场产物只陈述来源能够支持的内容，不把实验室指标直接等同于规模化商业效果。"
                   "每个结论保留证据入口，并把仍缺少交叉验证的问题列为下一轮 Mission。" * 3)
                + f" [{evidence_id}]"
            )
        return "# 量子传感 Starter Note\n\n" + "\n\n".join(paragraphs)


def _client(tmp_path):
    results = [
        {
            "title": "Quantum sensing review",
            "url": "https://arxiv.org/abs/2401.00001",
            "snippet": "A review of quantum sensing foundations and mechanisms.",
        },
        {
            "title": "Quantum technology policy",
            "url": "https://www.oecd.org/technology/quantum-sensing.html",
            "snippet": "Policy and ecosystem overview for quantum technologies.",
        },
        {
            "title": "Quantum sensing implementation",
            "url": "https://github.com/example/quantum-sensing-review",
            "snippet": "Open implementation notes and engineering constraints.",
        },
        {
            "title": "Quantum sensing measurement limits",
            "url": "https://arxiv.org/abs/2402.00002",
            "snippet": "Measurement limits and disputed system-level advantages.",
        },
    ]
    pages = {
        item["url"]: {
            "title": item["title"],
            "raw_text": (item["snippet"] + " Evidence-backed readable source body.") * 20,
        }
        for item in results
    }
    class ChallengeSearch:
        async def search(self, query):
            selected = results[2:] if "industry" in query.query else results[:2]
            return [SearchResult(**item) for item in selected[:query.max_results]]

    search = ChallengeSearch()
    extraction = FakeContentExtractionProvider(pages)
    llm = ChallengeLLM()
    return TestClient(create_app(
        database_path=tmp_path / "sectorbreaker.db",
        export_root=tmp_path / "exports",
        search_provider=search,
        content_extraction_provider=extraction,
        backup_content_extraction_provider=extraction,
        llm_provider=llm,
        backup_llm_provider=llm,
        embedding_mode="disabled",
    ))


def test_live_challenge_proposes_note_and_apply_completes_mission(tmp_path, monkeypatch):
    monkeypatch.delenv("SECTORBREAKER_A2A_RESEARCHER_URL", raising=False)
    client = _client(tmp_path)
    project = client.post("/api/projects", json={
        "title": "量子传感现场挑战",
        "domain": "量子传感",
        "market_scope": "global",
        "depth": "quick",
        "source_policy": "reliable_first",
    }).json()

    started = client.post(f"/api/projects/{project['id']}/challenge-runs", json={
        "domain": "量子传感",
        "deadline_seconds": 300,
    })
    assert started.status_code == 200, started.text
    run_id = started.json()["id"]

    mission_response = client.get(f"/api/runs/{run_id}/agent-mission")
    assert mission_response.status_code == 200, mission_response.text
    mission = mission_response.json()
    assert mission["status"] == "waiting_for_review", {
        "failure": mission["failure_reason"],
        "orders": [(item["task_type"], item["status"], item["assigned_agent_id"]) for item in mission["work_orders"]],
        "settlements": [(item["accepted"], item["reason"]) for item in mission["settlements"]],
    }
    assert len([item for item in mission["work_orders"] if item["task_type"] == "research"]) == 2
    assert len(mission["settlements"]) == 4
    assert all(item["accepted"] for item in mission["settlements"])
    assert mission["change_set_id"]

    events = client.get(f"/api/runs/{run_id}/trace").json()["events"]
    event_types = {item["event_type"] for item in events}
    assert {"mission_planned", "task_awarded", "deliverable_accepted", "task_settled"} <= event_types

    change_set_id = mission["change_set_id"]
    assert client.post(f"/api/projects/{project['id']}/change-sets/{change_set_id}/approve").status_code == 200
    applied = client.post(f"/api/projects/{project['id']}/change-sets/{change_set_id}/apply")
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied"
    assert client.get(f"/api/runs/{run_id}/agent-mission").json()["status"] == "completed"
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "completed"


def test_agent_registry_exposes_identity_capabilities_and_transport(tmp_path):
    client = _client(tmp_path)
    project = client.post("/api/projects", json={
        "title": "机器人现场挑战",
        "domain": "机器人",
        "market_scope": "mixed",
        "depth": "quick",
    }).json()
    response = client.get(f"/api/projects/{project['id']}/agent-registry")
    assert response.status_code == 200
    registry = response.json()
    assert {item["agent_id"] for item in registry} >= {
        "foundation_researcher_local",
        "ecosystem_researcher_a2a",
        "counterevidence_verifier_local",
        "knowledge_editor_local",
    }
    remote = next(item for item in registry if item["agent_id"] == "ecosystem_researcher_a2a")
    assert remote["transport"] == "a2a"
    assert "research_ecosystem" in remote["capabilities"]


def test_demo_readiness_fails_closed_without_independent_channels(tmp_path, monkeypatch):
    monkeypatch.delenv("SECTORBREAKER_A2A_RESEARCHER_URL", raising=False)
    response = _client(tmp_path).get("/api/demo/readiness")
    assert response.status_code == 200
    readiness = response.json()
    assert readiness["ready"] is False
    by_key = {item["key"]: item for item in readiness["checks"]}
    assert by_key["primary_llm"]["ready"] is True
    assert by_key["llm_independence"]["ready"] is False
    assert by_key["search"]["ready"] is False
    assert by_key["a2a"]["ready"] is False
    assert "api_key" not in response.text.lower()


def test_a2a_failure_is_visible_and_reassigned_to_local_agent(tmp_path, monkeypatch):
    class FailingA2ATransport:
        async def discover(self, endpoint):
            return {"skills": [{
                "id": "research_ecosystem",
                "tags": ["research_ecosystem", "web_search", "evidence_extract"],
            }]}

        async def execute(self, endpoint, work_order, *, domain, timeout_seconds):
            raise TimeoutError("remote worker timeout")

    import backend.app.agent_network.a2a_transport as a2a_module

    monkeypatch.setenv("SECTORBREAKER_A2A_RESEARCHER_URL", "http://127.0.0.1:8011")
    monkeypatch.setattr(a2a_module, "A2AClientTransport", FailingA2ATransport)
    client = _client(tmp_path)
    project = client.post("/api/projects", json={
        "title": "A2A 故障演示",
        "domain": "量子传感",
        "market_scope": "global",
        "depth": "quick",
    }).json()
    run = client.post(f"/api/projects/{project['id']}/challenge-runs", json={"domain": "量子传感"}).json()
    mission = client.get(f"/api/runs/{run['id']}/agent-mission").json()
    assert mission["status"] == "waiting_for_review"
    ecosystem = next(item for item in mission["work_orders"] if "research_ecosystem" in item["required_capabilities"])
    assert ecosystem["assigned_agent_id"] == "ecosystem_researcher_local"
    assert ecosystem["attempts"] == 2
    events = client.get(f"/api/runs/{run['id']}/trace").json()["events"]
    reassigned = [item for item in events if item["event_type"] == "task_reassigned"]
    assert reassigned
    assert reassigned[-1]["data"]["failed_agent_id"] == "ecosystem_researcher_a2a"
