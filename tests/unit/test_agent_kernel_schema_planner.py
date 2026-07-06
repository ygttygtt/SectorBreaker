import asyncio

from backend.app.agent_kernel.schema_planner import PlannedKnowledgeSchema, PlannedLayer, build_adaptive_schema


def test_build_adaptive_schema_uses_llm_planned_layers() -> None:
    class FakeLLM:
        async def complete(self, messages):
            raise AssertionError("schema planner should use structured completion")

        async def complete_structured(self, messages, response_schema):
            assert response_schema is PlannedKnowledgeSchema
            return PlannedKnowledgeSchema(
                generated_reason="API 中转站需要更重的技术实现和风险边界层。",
                layers=[
                    PlannedLayer(
                        id="L1_what_why",
                        title="本源与需求",
                        goal="解释是什么和为什么存在。",
                        guiding_questions=["它解决什么问题？"],
                        completion_criteria=["能解释基本定义和需求来源。"],
                        required_evidence_types=["overview", "case"],
                    ),
                    PlannedLayer(
                        id="technical_protocols",
                        title="协议与代理机制",
                        goal="拆解协议转换、反向代理和鉴权。",
                        priority_weight=2.2,
                        prerequisite_layer_ids=["L1_what_why"],
                        guiding_questions=["协议为什么需要转换？"],
                        completion_criteria=["能说明协议转换和代理链路。"],
                        required_evidence_types=["technical_doc", "tutorial"],
                    ),
                    PlannedLayer(
                        id="risk_surface",
                        title="风险与边界",
                        goal="识别合规、平台和数据安全风险。",
                        guiding_questions=["哪些风险会阻断使用？"],
                        completion_criteria=["能说明主要风险和不可做事项。"],
                        required_evidence_types=["policy", "risk_case"],
                    ),
                ],
            )

    schema = asyncio.run(build_adaptive_schema(
        domain="API 中转站",
        user_goal="建库",
        market_scope="mixed",
        source_policy="open_web",
        llm_provider=FakeLLM(),  # type: ignore[arg-type]
    ))

    assert schema.strategy == "llm_adaptive_practical_cognition"
    assert schema.layer("technical_protocols") is not None
    assert schema.layer("technical_protocols").priority_weight == 2.2
    assert "技术实现" in schema.generated_reason


def test_build_adaptive_schema_falls_back_without_llm() -> None:
    schema = asyncio.run(build_adaptive_schema(
        domain="量化交易",
        user_goal="建库",
        market_scope="mixed",
        source_policy="open_web",
        llm_provider=None,
    ))

    assert schema.layer("L1_what_why") is not None
    assert "fallback" in schema.generated_reason
