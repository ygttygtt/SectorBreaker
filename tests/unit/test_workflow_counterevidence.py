import asyncio

from backend.app.graph.workflow import run_research_workflow
from backend.app.providers.interfaces import SearchQuery, SearchResult
from backend.app.providers.fakes import FakeContentExtractionProvider, FakeLLMProvider, FakeSearchProvider
from backend.app.schemas import MarketScope, ResearchDepth, ResearchProject


def _default_fake_llm():
    return FakeLLMProvider(
        response={
            "domain_definition": "测试行业",
            "boundaries": "测试边界",
            "common_confusions": [],
            "key_questions": [],
            "data_caliber": [],
            "sections": ["行业定义"],
            "key_questions_list": [],
            "learning_path": [],
            "title": "测试",
            "content": "# 测试内容\n\n行业分析。",
        }
    )


class QueryAwareSearchProvider:
    def __init__(self) -> None:
        self.search_requests: list[SearchQuery] = []

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        self.search_requests.append(query)
        if "争议" in query.query or "质疑" in query.query:
            return [
                SearchResult(
                    title="普通网页上的风险质疑",
                    url="https://example.com/risk-analysis",
                    snippet="有来源质疑相关口径和增长叙事。",
                )
            ]
        return [
            SearchResult(
                title="国家统计局官方数据",
                url="https://www.stats.gov.cn/sj/zxfb/202401/t20240101_123.html",
                snippet="官方数据显示相关行业保持增长。",
            )
        ]


class NonConflictingChallengeSearchProvider:
    def __init__(self) -> None:
        self.search_requests: list[SearchQuery] = []

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        self.search_requests.append(query)
        if "争议" in query.query or "质疑" in query.query:
            return [
                SearchResult(
                    title="无关背景资料",
                    url="https://example.com/background",
                    snippet="这是一篇普通背景资料，介绍行业概况和常见参与方。",
                )
            ]
        return [
            SearchResult(
                title="国家统计局官方数据",
                url="https://www.stats.gov.cn/sj/zxfb/202401/t20240101_123.html",
                snippet="官方数据显示相关行业保持增长。",
            )
        ]


class WeakCorroborationSearchProvider:
    def __init__(self) -> None:
        self.search_requests: list[SearchQuery] = []

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        self.search_requests.append(query)
        return [
            SearchResult(
                title="普通网页支持说法",
                url="https://example.com/supporting-blog",
                snippet="文章认为政策机会增长很快。",
            )
        ]


def test_workflow_builds_counterevidence_tasks_and_evidence() -> None:
    project = ResearchProject(
        id="project-counterevidence",
        title="AI Agent Tools",
        domain="AI Agent 工具",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
    )

    state = asyncio.run(
        run_research_workflow(
            project,
            llm_provider=_default_fake_llm(),
            search_provider=FakeSearchProvider(
                results=[
                    {
                        "title": "官方市场数据",
                        "url": "https://example.org/official-market-data",
                        "snippet": "官方统计显示该市场仍在快速变化。",
                    },
                    {
                        "title": "争议与风险分析",
                        "url": "https://example.com/risk-analysis",
                        "snippet": "也有来源质疑相关口径和增长叙事。",
                    },
                ]
            ),
            content_extraction_provider=FakeContentExtractionProvider(
                {
                    "https://example.org/official-market-data": {
                        "title": "Official Market Data Release",
                        "raw_text": "Official data release from a neutral source with market statistics.",
                        "domain": "example.org",
                    },
                    "https://example.com/risk-analysis": {
                        "title": "Risk Analysis",
                        "raw_text": "Some analysts challenge the growth story and data caliber.",
                        "domain": "example.com",
                    },
                }
            ),
            assistant_brief="AI agent 市场规模增长很快，很多厂商都在宣传。",
        )
    )

    verification_evidence = [item for item in state.evidence if item.id.startswith("EV-VERIFY-")]

    assert verification_evidence
    assert any(item.collected_by == "counterevidence_search" for item in verification_evidence)
    assert any(item.verification_status.value in {"partially_verified", "conflicting"} for item in verification_evidence)
    assert any(item.source_title == "Official Market Data Release" for item in verification_evidence)
    original = next(item for item in state.evidence if item.id == "EV-ASSISTANT-BRIEF-001")
    assert original.corroborating_evidence_ids or original.conflicting_evidence_ids
    linked_ids = set(original.corroborating_evidence_ids + original.conflicting_evidence_ids)
    assert linked_ids.issubset({item.id for item in verification_evidence})


def test_workflow_applies_reliable_only_domain_constraints_to_search() -> None:
    search_provider = FakeSearchProvider(
        results=[
            {
                "title": "官方市场数据",
                "url": "https://example.org/official-market-data",
                "snippet": "官方统计显示该市场仍在快速变化。",
            }
        ]
    )
    project = ResearchProject(
        id="project-reliable-only",
        title="政策机会",
        domain="政策机会",
        market_scope=MarketScope.CHINA,
        depth=ResearchDepth.QUICK,
        source_policy="reliable_only",
    )

    asyncio.run(
        run_research_workflow(
            project,
            llm_provider=_default_fake_llm(),
            search_provider=search_provider,
        )
    )

    assert search_provider.search_requests
    assert any(request.allowed_domains for request in search_provider.search_requests)
    assert "gov.cn" in (search_provider.search_requests[0].allowed_domains or [])
    assert "medium.com" in (search_provider.search_requests[0].blocked_domains or [])


def test_reliable_only_allows_weak_leads_and_conflicting_counterevidence_without_fact_support() -> None:
    project = ResearchProject(
        id="project-reliable-only-counterevidence",
        title="政策机会",
        domain="政策机会",
        market_scope=MarketScope.CHINA,
        depth=ResearchDepth.QUICK,
        source_policy="reliable_only",
    )

    state = asyncio.run(
        run_research_workflow(
            project,
            llm_provider=_default_fake_llm(),
            search_provider=QueryAwareSearchProvider(),
            assistant_brief="政策机会增长很快，但这个判断需要官方口径验证。",
        )
    )

    assert state.qa_report is not None
    assert not any("严格可靠模式下存在弱来源证据" in issue for issue in state.qa_report.blocking_issues)
    conflicting = [item for item in state.evidence if item.verification_status.value == "conflicting"]
    assert conflicting
    assert any(item.source_type == "web" for item in conflicting)


def test_challenge_search_without_conflict_signal_does_not_link_conflicting_evidence() -> None:
    project = ResearchProject(
        id="project-non-conflicting-challenge",
        title="政策机会",
        domain="政策机会",
        market_scope=MarketScope.CHINA,
        depth=ResearchDepth.QUICK,
        source_policy="reliable_only",
    )

    state = asyncio.run(
        run_research_workflow(
            project,
            llm_provider=_default_fake_llm(),
            search_provider=NonConflictingChallengeSearchProvider(),
            assistant_brief="政策机会增长很快，但这个判断需要官方口径验证。",
        )
    )

    original = next(item for item in state.evidence if item.id == "EV-ASSISTANT-BRIEF-001")
    assert original.conflicting_evidence_ids == []
    assert not any(item.verification_status.value == "conflicting" for item in state.evidence)


def test_reliable_only_weak_corroboration_result_is_not_marked_as_fact() -> None:
    project = ResearchProject(
        id="project-weak-corroboration",
        title="政策机会",
        domain="政策机会",
        market_scope=MarketScope.CHINA,
        depth=ResearchDepth.QUICK,
        source_policy="reliable_only",
    )

    state = asyncio.run(
        run_research_workflow(
            project,
            llm_provider=_default_fake_llm(),
            search_provider=WeakCorroborationSearchProvider(),
            assistant_brief="政策机会增长很快，但这个判断需要官方口径验证。",
        )
    )

    weak_verification = [
        item
        for item in state.evidence
        if item.collected_by == "counterevidence_search" and item.source_type == "web"
    ]

    assert weak_verification
    assert all(item.claim_strength.value != "fact" for item in weak_verification)
