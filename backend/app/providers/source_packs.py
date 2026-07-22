"""Reliable source packs shared by search, verification, and QA."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlparse

from backend.app.schemas import MarketScope, SourceType


class SourceConnectorType(StrEnum):
    OFFICIAL_API = "official_api"
    COMMERCIAL_API = "commercial_api"
    LIBRARY_ADAPTER = "library_adapter"
    SEARCH_DOMAIN_PACK = "search_domain_pack"
    EXTRACTION_FALLBACK = "extraction_fallback"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class SourceConnector:
    key: str
    display_name: str
    connector_type: SourceConnectorType
    source_type: SourceType
    trust_level: str
    domains: tuple[str, ...] = ()
    required_env_keys: tuple[str, ...] = ()
    setup_url: str | None = None
    can_support_facts: bool = True
    requires_manual_review: bool = False
    notes: str = ""


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
    display_name: str = ""
    connectors: tuple[SourceConnector, ...] = ()


@dataclass(frozen=True)
class SourceRegistry:
    packs: tuple[SourcePack, ...] = field(default_factory=tuple)

    def get_pack(self, name: str) -> SourcePack | None:
        return next((pack for pack in self.packs if pack.name == name), None)

    def packs_for_market(self, market_scope: str | None) -> tuple[SourcePack, ...]:
        scope = market_scope or MarketScope.MIXED.value
        return tuple(pack for pack in self.packs if scope in pack.market_scopes)

    def connectors_for_pack(self, pack_name: str) -> tuple[SourceConnector, ...]:
        pack = self.get_pack(pack_name)
        return pack.connectors if pack else ()

    def connectors_for_market(self, market_scope: str | None) -> tuple[SourceConnector, ...]:
        connectors: list[SourceConnector] = []
        for pack in self.packs_for_market(market_scope):
            connectors.extend(pack.connectors)
        return tuple(connectors)

    def reliable_domains_for_market(self, market_scope: str | None) -> list[str]:
        domains: list[str] = []
        for pack in self.packs_for_market(market_scope):
            domains.extend(rule.domain for rule in pack.reliable_rules)
        return list(dict.fromkeys(domains))

    def blocked_domains_for_market(self, market_scope: str | None) -> list[str]:
        domains: list[str] = []
        for pack in self.packs_for_market(market_scope):
            domains.extend(pack.blocked_domains)
        return list(dict.fromkeys(domains))

    def match_reliable_rule(self, domain: str | None) -> ReliableSourceRule | None:
        if not domain:
            return None
        for pack in self.packs:
            for rule in pack.reliable_rules:
                if domain_matches(domain, rule.domain):
                    return rule
        return None


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
    display_name="中国公共权威信源",
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
    display_name="全球公共权威信源",
)

SOURCE_PACKS: tuple[SourcePack, ...] = (CHINA_RELIABLE_PACK, GLOBAL_RELIABLE_PACK)


# ── Company China Pack (extended connectors) ──────────────────

_COMPANY_CHINA_RULES = (
    ReliableSourceRule("cninfo.com.cn", SourceType.COMPANY_DISCLOSURE, "china_listed_company_disclosure"),
    ReliableSourceRule("sse.com.cn", SourceType.COMPANY_DISCLOSURE, "shanghai_stock_exchange"),
    ReliableSourceRule("szse.cn", SourceType.COMPANY_DISCLOSURE, "shenzhen_stock_exchange"),
    ReliableSourceRule("neeq.com.cn", SourceType.COMPANY_DISCLOSURE, "neeq_disclosure"),
    ReliableSourceRule("bse.com.cn", SourceType.COMPANY_DISCLOSURE, "beijing_stock_exchange"),
    ReliableSourceRule("gsxt.gov.cn", SourceType.PUBLIC_DATABASE, "china_business_registration"),
    ReliableSourceRule("csrc.gov.cn", SourceType.GOVERNMENT, "china_securities_regulator"),
)

_COMPANY_CHINA_CONNECTORS: tuple[SourceConnector, ...] = (
    SourceConnector(
        key="cninfo_public",
        display_name="巨潮资讯公开披露",
        connector_type=SourceConnectorType.SEARCH_DOMAIN_PACK,
        source_type=SourceType.COMPANY_DISCLOSURE,
        trust_level="high",
        domains=("cninfo.com.cn",),
        notes="通过搜索 provider 发现公开披露 URL。",
    ),
    SourceConnector(
        key="sse_disclosure",
        display_name="上交所披露",
        connector_type=SourceConnectorType.SEARCH_DOMAIN_PACK,
        source_type=SourceType.COMPANY_DISCLOSURE,
        trust_level="high",
        domains=("sse.com.cn",),
    ),
    SourceConnector(
        key="szse_disclosure",
        display_name="深交所披露",
        connector_type=SourceConnectorType.SEARCH_DOMAIN_PACK,
        source_type=SourceType.COMPANY_DISCLOSURE,
        trust_level="high",
        domains=("szse.cn",),
    ),
    SourceConnector(
        key="bse_disclosure",
        display_name="北交所披露",
        connector_type=SourceConnectorType.SEARCH_DOMAIN_PACK,
        source_type=SourceType.COMPANY_DISCLOSURE,
        trust_level="high",
        domains=("bse.com.cn",),
    ),
    SourceConnector(
        key="gsxt_manual",
        display_name="国家企业信用信息公示",
        connector_type=SourceConnectorType.MANUAL_REVIEW,
        source_type=SourceType.PUBLIC_DATABASE,
        trust_level="high",
        domains=("gsxt.gov.cn",),
        requires_manual_review=True,
        notes="高可信但可能有验证码，需人工复核。",
    ),
    SourceConnector(
        key="qcc_openapi",
        display_name="企查查开放平台",
        connector_type=SourceConnectorType.COMMERCIAL_API,
        source_type=SourceType.PUBLIC_DATABASE,
        trust_level="high",
        domains=("openapi.qcc.com",),
        required_env_keys=("QCC_API_KEY",),
        setup_url="https://openapi.qcc.com/dataApi",
        notes="付费商业 API，MVP 可不配置。",
    ),
    SourceConnector(
        key="tianyancha_openapi",
        display_name="天眼查开放平台",
        connector_type=SourceConnectorType.COMMERCIAL_API,
        source_type=SourceType.PUBLIC_DATABASE,
        trust_level="high",
        domains=("open.tianyancha.com",),
        required_env_keys=("TIANYANCHA_API_KEY",),
        setup_url="https://open.tianyancha.com/",
        notes="付费商业 API，MVP 可不配置。",
    ),
    SourceConnector(
        key="akshare_adapter",
        display_name="AKShare 数据适配器",
        connector_type=SourceConnectorType.LIBRARY_ADAPTER,
        source_type=SourceType.PUBLIC_DATABASE,
        trust_level="medium",
        notes="开源 Python 库，数据来源于公开接口，权威性低于原始披露。",
    ),
    SourceConnector(
        key="tushare_api",
        display_name="Tushare 数据接口",
        connector_type=SourceConnectorType.LIBRARY_ADAPTER,
        source_type=SourceType.PUBLIC_DATABASE,
        trust_level="medium",
        required_env_keys=("TUSHARE_TOKEN",),
        setup_url="https://tushare.pro/",
        notes="需注册 token，数据来源于公开接口。",
    ),
)

COMPANY_CHINA_PACK = SourcePack(
    name="company_china_pack",
    market_scopes=(MarketScope.CHINA.value, MarketScope.MIXED.value),
    reliable_rules=_COMPANY_CHINA_RULES,
    blocked_domains=("medium.com", "substack.com", "zhihu.com", "xiaohongshu.com"),
    display_name="中国企业与披露信源",
    connectors=_COMPANY_CHINA_CONNECTORS,
)


# ── Tech Frontier Pack ────────────────────────────────────────

_TECH_FRONTIER_CONNECTORS: tuple[SourceConnector, ...] = (
    SourceConnector(
        key="github_api",
        display_name="GitHub API",
        connector_type=SourceConnectorType.OFFICIAL_API,
        source_type=SourceType.OFFICIAL,
        trust_level="high",
        domains=("api.github.com",),
        required_env_keys=("GITHUB_TOKEN",),
        setup_url="https://github.com/settings/tokens",
    ),
    SourceConnector(
        key="arxiv_api",
        display_name="arXiv API",
        connector_type=SourceConnectorType.OFFICIAL_API,
        source_type=SourceType.OFFICIAL,
        trust_level="high",
        domains=("arxiv.org",),
        setup_url="https://info.arxiv.org/help/api/",
    ),
    SourceConnector(
        key="semantic_scholar_api",
        display_name="Semantic Scholar API",
        connector_type=SourceConnectorType.OFFICIAL_API,
        source_type=SourceType.OFFICIAL,
        trust_level="high",
        domains=("api.semanticscholar.org",),
        setup_url="https://www.semanticscholar.org/product/api",
    ),
    SourceConnector(
        key="stack_exchange_api",
        display_name="Stack Exchange API",
        connector_type=SourceConnectorType.OFFICIAL_API,
        source_type=SourceType.OFFICIAL,
        trust_level="high",
        domains=("api.stackexchange.com",),
        setup_url="https://api.stackexchange.com/docs",
    ),
    SourceConnector(
        key="hn_algolia_api",
        display_name="Hacker News Algolia API",
        connector_type=SourceConnectorType.OFFICIAL_API,
        source_type=SourceType.MEDIA,
        trust_level="medium",
        domains=("hn.algolia.com",),
        setup_url="https://hn.algolia.com/api",
    ),
    SourceConnector(
        key="hn_firebase_api",
        display_name="Hacker News Firebase API",
        connector_type=SourceConnectorType.OFFICIAL_API,
        source_type=SourceType.MEDIA,
        trust_level="medium",
        domains=("hacker-news.firebaseio.com",),
        setup_url="https://github.com/HackerNews/API",
    ),
    SourceConnector(
        key="papers_with_code",
        display_name="Papers with Code API",
        connector_type=SourceConnectorType.OFFICIAL_API,
        source_type=SourceType.OFFICIAL,
        trust_level="high",
        domains=("paperswithcode.com",),
        setup_url="https://paperswithcode.com/api/v1/docs/",
    ),
    SourceConnector(
        key="firecrawl_extraction",
        display_name="Firecrawl 正文抽取",
        connector_type=SourceConnectorType.EXTRACTION_FALLBACK,
        source_type=SourceType.WEB,
        trust_level="medium",
        required_env_keys=("FIRECRAWL_API_KEY",),
        setup_url="https://www.firecrawl.dev/",
        notes="从已发现 URL 抽取正文，不是事实来源。",
    ),
    SourceConnector(
        key="jina_reader_extraction",
        display_name="Jina Reader 正文抽取",
        connector_type=SourceConnectorType.EXTRACTION_FALLBACK,
        source_type=SourceType.WEB,
        trust_level="medium",
        setup_url="https://jina.ai/reader/",
        notes="从已发现 URL 抽取正文，不是事实来源。",
    ),
)


def build_default_source_registry() -> SourceRegistry:
    return SourceRegistry(packs=(
        COMPANY_CHINA_PACK,
        SourcePack(
            name="tech_frontier_pack",
            market_scopes=(MarketScope.GLOBAL.value, MarketScope.MIXED.value),
            reliable_rules=(
                ReliableSourceRule("arxiv.org", SourceType.OFFICIAL, "arxiv_preprint"),
                ReliableSourceRule("github.com", SourceType.OFFICIAL, "github_repository"),
                ReliableSourceRule("semanticscholar.org", SourceType.PUBLIC_DATABASE, "semantic_scholar"),
                ReliableSourceRule("paperswithcode.com", SourceType.PUBLIC_DATABASE, "papers_with_code"),
            ),
            blocked_domains=("medium.com", "substack.com", "reddit.com"),
            display_name="技术前沿信源",
            connectors=_TECH_FRONTIER_CONNECTORS,
        ),
        CHINA_RELIABLE_PACK,
        GLOBAL_RELIABLE_PACK,
    ))


DEFAULT_SOURCE_REGISTRY = build_default_source_registry()


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
    return DEFAULT_SOURCE_REGISTRY.packs_for_market(market_scope)


def reliable_domains_for_market(market_scope: str | None) -> list[str]:
    return DEFAULT_SOURCE_REGISTRY.reliable_domains_for_market(market_scope)


def blocked_domains_for_market(market_scope: str | None) -> list[str]:
    return DEFAULT_SOURCE_REGISTRY.blocked_domains_for_market(market_scope)


def match_reliable_rule(domain: str | None) -> ReliableSourceRule | None:
    return DEFAULT_SOURCE_REGISTRY.match_reliable_rule(domain)
