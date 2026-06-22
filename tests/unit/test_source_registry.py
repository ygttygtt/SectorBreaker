"""Tests for SourceRegistry, SourceConnector, and SourceConnectorType."""

from backend.app.providers.source_packs import (
    SourceConnectorType,
    build_default_source_registry,
)


def test_registry_lists_china_company_pack_connectors() -> None:
    registry = build_default_source_registry()

    pack = registry.get_pack("company_china_pack")

    assert pack is not None
    connector_keys = {connector.key for connector in pack.connectors}
    assert {"cninfo_public", "sse_disclosure", "szse_disclosure", "gsxt_manual", "qcc_openapi", "tianyancha_openapi"}.issubset(connector_keys)
    assert registry.reliable_domains_for_market("china")
    assert "cninfo.com.cn" in registry.reliable_domains_for_market("china")


def test_registry_marks_manual_and_commercial_connectors() -> None:
    registry = build_default_source_registry()

    connectors = {connector.key: connector for connector in registry.connectors_for_market("china")}

    assert connectors["gsxt_manual"].connector_type == SourceConnectorType.MANUAL_REVIEW
    assert connectors["gsxt_manual"].requires_manual_review is True
    assert connectors["qcc_openapi"].connector_type == SourceConnectorType.COMMERCIAL_API
    assert connectors["qcc_openapi"].required_env_keys == ("QCC_API_KEY",)


def test_registry_lists_tech_frontier_official_apis() -> None:
    registry = build_default_source_registry()

    connectors = {connector.key: connector for connector in registry.connectors_for_pack("tech_frontier_pack")}

    assert connectors["github_api"].connector_type == SourceConnectorType.OFFICIAL_API
    assert connectors["github_api"].required_env_keys == ("GITHUB_TOKEN",)
    assert connectors["arxiv_api"].required_env_keys == ()
    assert connectors["stack_exchange_api"].setup_url == "https://api.stackexchange.com/docs"
