"""Reliable source packs shared by search, verification, and QA."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from backend.app.schemas import MarketScope, SourceType


@dataclass(frozen=True)
class ReliableSourceRule:
    domain: str
    source_type: SourceType
    quality_reason: str
    original_source: bool = True


@dataclass(frozen=True)
class SourcePack:
    name: str
    market_scopes: tuple[str, ...]
    reliable_rules: tuple[ReliableSourceRule, ...]
    blocked_domains: tuple[str, ...] = ()


CHINA_RELIABLE_PACK = SourcePack(
    name="china_reliable_v1",
    market_scopes=(MarketScope.CHINA.value, MarketScope.MIXED.value),
    reliable_rules=(
        ReliableSourceRule("gov.cn", SourceType.GOVERNMENT, "china_government_domain"),
        ReliableSourceRule("stats.gov.cn", SourceType.GOVERNMENT, "china_statistics_bureau"),
        ReliableSourceRule("miit.gov.cn", SourceType.GOVERNMENT, "china_industry_regulator"),
        ReliableSourceRule("samr.gov.cn", SourceType.GOVERNMENT, "china_market_regulator"),
        ReliableSourceRule("mofcom.gov.cn", SourceType.GOVERNMENT, "china_commerce_ministry"),
        ReliableSourceRule("pbc.gov.cn", SourceType.GOVERNMENT, "china_central_bank"),
        ReliableSourceRule("cninfo.com.cn", SourceType.COMPANY_DISCLOSURE, "china_listed_company_disclosure"),
        ReliableSourceRule("sse.com.cn", SourceType.COMPANY_DISCLOSURE, "shanghai_stock_exchange"),
        ReliableSourceRule("szse.cn", SourceType.COMPANY_DISCLOSURE, "shenzhen_stock_exchange"),
        ReliableSourceRule("neeq.com.cn", SourceType.COMPANY_DISCLOSURE, "neeq_disclosure"),
    ),
    blocked_domains=("medium.com", "substack.com", "zhihu.com", "xiaohongshu.com"),
)

GLOBAL_RELIABLE_PACK = SourcePack(
    name="global_reliable_v1",
    market_scopes=(MarketScope.GLOBAL.value, MarketScope.MIXED.value),
    reliable_rules=(
        ReliableSourceRule("gov", SourceType.GOVERNMENT, "government_domain"),
        ReliableSourceRule("sec.gov", SourceType.COMPANY_DISCLOSURE, "sec_company_disclosure"),
        ReliableSourceRule("investor.gov", SourceType.GOVERNMENT, "investor_education_regulator"),
        ReliableSourceRule("worldbank.org", SourceType.PUBLIC_DATABASE, "world_bank_database"),
        ReliableSourceRule("oecd.org", SourceType.PUBLIC_DATABASE, "oecd_database"),
        ReliableSourceRule("imf.org", SourceType.PUBLIC_DATABASE, "imf_database"),
        ReliableSourceRule("who.int", SourceType.PUBLIC_DATABASE, "who_database"),
        ReliableSourceRule("europa.eu", SourceType.GOVERNMENT, "eu_public_domain"),
        ReliableSourceRule("data.gov", SourceType.PUBLIC_DATABASE, "us_open_data"),
    ),
    blocked_domains=("medium.com", "substack.com", "reddit.com", "quora.com"),
)

SOURCE_PACKS: tuple[SourcePack, ...] = (CHINA_RELIABLE_PACK, GLOBAL_RELIABLE_PACK)


def extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    return (parsed.netloc or "").lower() or None


def normalize_domain(domain: str) -> str:
    lowered = domain.lower().strip()
    return lowered[4:] if lowered.startswith("www.") else lowered


def domain_matches(domain: str, rule_domain: str) -> bool:
    normalized = normalize_domain(domain)
    rule = normalize_domain(rule_domain).lstrip(".")
    return normalized == rule or normalized.endswith(f".{rule}")


def packs_for_market(market_scope: str | None) -> tuple[SourcePack, ...]:
    scope = market_scope or MarketScope.MIXED.value
    return tuple(pack for pack in SOURCE_PACKS if scope in pack.market_scopes)


def reliable_domains_for_market(market_scope: str | None) -> list[str]:
    domains: list[str] = []
    for pack in packs_for_market(market_scope):
        domains.extend(rule.domain for rule in pack.reliable_rules)
    return list(dict.fromkeys(domains))


def blocked_domains_for_market(market_scope: str | None) -> list[str]:
    domains: list[str] = []
    for pack in packs_for_market(market_scope):
        domains.extend(pack.blocked_domains)
    return list(dict.fromkeys(domains))


def match_reliable_rule(domain: str | None) -> ReliableSourceRule | None:
    if not domain:
        return None
    for pack in SOURCE_PACKS:
        for rule in pack.reliable_rules:
            if domain_matches(domain, rule.domain):
                return rule
    return None
