import asyncio

from backend.app.providers.counterevidence import HeuristicCounterevidenceProvider


def test_counterevidence_provider_builds_corroborate_and_challenge_tasks() -> None:
    provider = HeuristicCounterevidenceProvider()

    tasks = asyncio.run(
        provider.build_verification_tasks(
            claim_id="CL-001",
            claim_text="AI agent 市场规模增长很快，很多厂商都在宣传。",
            market_scope="china",
        )
    )

    assert len(tasks) == 2
    assert tasks[0].verification_goal == "corroborate"
    assert tasks[1].verification_goal == "challenge"
    assert any("官方 数据" in query for query in tasks[0].query_variants)
    assert "stats.gov.cn" in (tasks[0].preferred_domains or [])
