"""Source-policy search constraints independent of retired workflow code."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from backend.app.providers.source_packs import DEFAULT_SOURCE_REGISTRY, blocked_domains_for_market, reliable_domains_for_market
from backend.app.schemas import SourceEnforcement, SourcePolicy


@dataclass(frozen=True)
class ProjectSearchConstraints:
    primary_allowed_domains: list[str]
    blocked_domains: list[str]
    fallback_allowed_domains: list[str] | None
    source_pack_ids: list[str]
    enforcement: str


def build_project_search_constraints(
    project: Mapping[str, Any],
    *,
    preferred_domains: list[str] | None = None,
) -> ProjectSearchConstraints:
    policy = SourcePolicy(project.get("source_policy") or SourcePolicy.RELIABLE_FIRST.value)
    market_scope = project.get("market_scope")
    raw_preferences = project.get("source_preferences") or {}
    if hasattr(raw_preferences, "model_dump"):
        raw_preferences = raw_preferences.model_dump(mode="json")
    pack_ids = list(dict.fromkeys(str(item).strip() for item in raw_preferences.get("source_pack_ids", []) if str(item).strip()))
    custom_allowed = _normalize_domains(raw_preferences.get("custom_allowed_domains", []))
    custom_blocked = _normalize_domains(raw_preferences.get("blocked_domains", []))
    enforcement = SourceEnforcement(raw_preferences.get("enforcement") or SourceEnforcement.PREFER.value)

    pack_allowed: list[str] = []
    pack_blocked: list[str] = []
    for pack_id in pack_ids:
        pack = DEFAULT_SOURCE_REGISTRY.get_pack(pack_id)
        if pack is None:
            continue
        pack_allowed.extend(rule.domain for rule in pack.reliable_rules)
        pack_blocked.extend(pack.blocked_domains)

    base_allowed, base_blocked = _base_policy_constraints(policy, market_scope)
    requested = _normalize_domains(preferred_domains or [])
    project_allowed = list(dict.fromkeys(pack_allowed + custom_allowed))
    blocked = list(dict.fromkeys(base_blocked + pack_blocked + custom_blocked))

    if project_allowed:
        narrowed = [
            domain for domain in requested
            if any(_domains_overlap(domain, allowed) for allowed in project_allowed)
        ]
        primary = narrowed or project_allowed
        fallback = base_allowed if enforcement == SourceEnforcement.PREFER else None
    else:
        primary = list(dict.fromkeys(requested + base_allowed))
        fallback = None

    return ProjectSearchConstraints(
        primary_allowed_domains=primary,
        blocked_domains=blocked,
        fallback_allowed_domains=fallback,
        source_pack_ids=pack_ids,
        enforcement=enforcement.value,
    )


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
    constraints = build_project_search_constraints(project, preferred_domains=preferred_domains)
    return constraints.primary_allowed_domains, constraints.blocked_domains


def _base_policy_constraints(policy: SourcePolicy, market_scope: str | None) -> tuple[list[str], list[str]]:
    if policy == SourcePolicy.OPEN_WEB:
        return [], []
    if policy == SourcePolicy.USER_MATERIALS_ONLY:
        return [], []
    return reliable_domains_for_market(market_scope), blocked_domains_for_market(market_scope)


def _normalize_domains(domains: list[str]) -> list[str]:
    return list(dict.fromkeys(
        str(domain).lower().strip().lstrip(".").rstrip(".")
        for domain in domains
        if str(domain).strip()
    ))


def _domains_overlap(left: str, right: str) -> bool:
    return left == right or left.endswith(f".{right}") or right.endswith(f".{left}")


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
