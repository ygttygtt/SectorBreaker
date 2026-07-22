"""Source-policy search constraints independent of retired workflow code."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from backend.app.providers.source_packs import blocked_domains_for_market, reliable_domains_for_market
from backend.app.schemas import SourcePolicy


def search_constraints_for_policy(
    project: Mapping[str, Any],
    *,
    verification: bool = False,
    preferred_domains: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Return provider-level allow/block lists for a project source policy.

    ``verification`` is retained in the provider contract because callers use
    it to describe intent. Reliable policies currently apply the same hard
    domain constraints to initial and verification searches.
    """

    del verification
    policy = SourcePolicy(project.get("source_policy") or SourcePolicy.RELIABLE_FIRST.value)
    market_scope = project.get("market_scope")
    preferred = preferred_domains or []

    if policy == SourcePolicy.OPEN_WEB:
        return list(dict.fromkeys(preferred)), []
    if policy == SourcePolicy.USER_MATERIALS_ONLY:
        return [], []

    allowed = list(dict.fromkeys(preferred + reliable_domains_for_market(market_scope)))
    blocked = blocked_domains_for_market(market_scope)
    return allowed, blocked


def url_matches_domain_policy(
    url: str,
    *,
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
) -> bool:
    """Apply the final host allow/block check after a vendor returns a URL."""
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    if not host:
        return False

    def matches(domain: str) -> bool:
        normalized = str(domain).lower().strip().lstrip(".").rstrip(".")
        return bool(normalized) and (host == normalized or host.endswith("." + normalized))

    if any(matches(domain) for domain in (blocked_domains or [])):
        return False
    return not allowed_domains or any(matches(domain) for domain in allowed_domains)
