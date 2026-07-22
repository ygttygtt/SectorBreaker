from backend.app.providers.source_policy import build_project_search_constraints


def test_required_project_pack_cannot_be_widened_by_agent_domains() -> None:
    constraints = build_project_search_constraints(
        {
            "market_scope": "mixed",
            "source_policy": "open_web",
            "source_preferences": {
                "source_pack_ids": ["tech_frontier_pack"],
                "custom_allowed_domains": [],
                "blocked_domains": ["spam.example"],
                "enforcement": "require",
            },
        },
        preferred_domains=["untrusted.example"],
    )

    assert "github.com" in constraints.primary_allowed_domains
    assert "untrusted.example" not in constraints.primary_allowed_domains
    assert constraints.fallback_allowed_domains is None
    assert "spam.example" in constraints.blocked_domains


def test_preferred_project_pack_has_explicit_base_policy_fallback() -> None:
    constraints = build_project_search_constraints(
        {
            "market_scope": "mixed",
            "source_policy": "open_web",
            "source_preferences": {
                "source_pack_ids": ["tech_frontier_pack"],
                "enforcement": "prefer",
            },
        }
    )

    assert "arxiv.org" in constraints.primary_allowed_domains
    assert constraints.fallback_allowed_domains == []
