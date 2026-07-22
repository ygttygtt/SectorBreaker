"""Local heuristic source verification provider."""

from __future__ import annotations

from backend.app.providers.interfaces import SourceAssessment
from backend.app.providers.source_packs import (
    DEFAULT_SOURCE_REGISTRY,
    SourceRegistry,
    extract_domain,
)
from backend.app.schemas import SourcePolicy, SourceQuality, SourceType, VerificationStatus


_ACADEMIC_HOST_SUFFIXES = (
    ".edu",
    ".edu.cn",
    ".ac.uk",
)

_MEDIA_HOST_KEYWORDS = (
    "news",
    "media",
    "press",
    "reuters",
    "bloomberg",
)

_COMMUNITY_HOST_KEYWORDS = (
    "reddit",
    "zhihu",
    "xiaohongshu",
    "weibo",
    "x.com",
    "twitter",
    "tieba",
)

_MARKETING_PATH_KEYWORDS = (
    "blog",
    "marketing",
    "case-study",
    "case_study",
    "landing",
    "lp",
    "promo",
    "campaign",
    "best-",
    "top-",
)

_AGGREGATOR_HOST_KEYWORDS = (
    "wikipedia",
    "baike",
    "fandom",
    "medium",
    "substack",
)


class HeuristicSourceVerificationProvider:
    def __init__(self, source_registry: SourceRegistry | None = None) -> None:
        self.source_registry = source_registry or DEFAULT_SOURCE_REGISTRY

    async def assess_source(
        self,
        *,
        url: str | None,
        title: str | None,
        snippet: str | None,
        extracted_text: str | None,
        source_policy: str,
    ) -> SourceAssessment:
        domain = extract_domain(url)
        combined_text = " ".join(part for part in [title, snippet, extracted_text] if part).lower()
        marketing_signals: list[str] = []
        reliability_signals: list[str] = []

        source_type = SourceType.WEB
        source_quality = SourceQuality.UNKNOWN
        is_original_source = False
        is_marketing_like = False

        if domain:
            lowered_domain = domain.lower()
            reliable_rule = self.source_registry.match_reliable_rule(lowered_domain)
            if reliable_rule:
                source_type = reliable_rule.source_type
                source_quality = SourceQuality.HIGH
                is_original_source = reliable_rule.original_source
                reliability_signals.append(f"source_pack:{reliable_rule.quality_reason}")
            elif lowered_domain.endswith(_ACADEMIC_HOST_SUFFIXES):
                source_type = SourceType.OFFICIAL
                source_quality = SourceQuality.HIGH
                is_original_source = True
                reliability_signals.append("academic_domain")
            elif any(keyword in lowered_domain for keyword in _COMMUNITY_HOST_KEYWORDS):
                source_type = SourceType.COMMUNITY
                source_quality = SourceQuality.LOW
            elif any(keyword in lowered_domain for keyword in _MEDIA_HOST_KEYWORDS):
                source_type = SourceType.MEDIA
                source_quality = SourceQuality.MEDIUM
            elif any(keyword in lowered_domain for keyword in _AGGREGATOR_HOST_KEYWORDS):
                source_type = SourceType.MEDIA
                source_quality = SourceQuality.LOW
                marketing_signals.append("aggregator_or_secondary_platform")

        lowered_url = (url or "").lower()
        if any(keyword in lowered_url for keyword in _MARKETING_PATH_KEYWORDS):
            is_marketing_like = True
            marketing_signals.append("marketing_like_url_pattern")

        if any(phrase in combined_text for phrase in ("立即咨询", "联系我们", "book demo", "free trial", "预约演示", "立即购买")):
            is_marketing_like = True
            marketing_signals.append("cta_language")

        if source_type == SourceType.WEB and domain and any(token in domain.lower() for token in ("docs", "help", "support")):
            source_type = SourceType.OFFICIAL
            source_quality = SourceQuality.HIGH
            is_original_source = True
            reliability_signals.append("official_support_domain")

        if source_type == SourceType.WEB and (
            (domain and any(token in domain.lower() for token in ("investor", "ir.")))
            or any(token in lowered_url for token in ("/investor", "/ir/", "annual-report", "earnings"))
        ):
            source_type = SourceType.COMPANY_DISCLOSURE
            source_quality = SourceQuality.HIGH
            is_original_source = True
            reliability_signals.append("company_disclosure_pattern")

        # This provider assesses the source, not the truth of a claim. Domain
        # quality alone can never promote evidence to fully verified.
        verification_status = VerificationStatus.PARTIALLY_VERIFIED
        if source_type in {SourceType.COMMUNITY, SourceType.ASSISTANT_BRIEF} or is_marketing_like:
            verification_status = VerificationStatus.UNVERIFIED

        source_policy_value = source_policy or SourcePolicy.RELIABLE_FIRST.value
        if source_policy_value == SourcePolicy.RELIABLE_ONLY.value and source_quality != SourceQuality.HIGH:
            verification_status = VerificationStatus.UNVERIFIED

        reliability_notes = _build_reliability_notes(
            source_type,
            source_quality,
            is_marketing_like,
            marketing_signals,
            reliability_signals,
        )

        return SourceAssessment(
            url=url,
            domain=domain,
            source_type=source_type.value,
            source_quality=source_quality.value,
            is_original_source=is_original_source,
            is_marketing_like=is_marketing_like,
            marketing_signals=marketing_signals,
            reliability_notes=reliability_notes,
            recommended_verification_status=verification_status.value,
        )


def _build_reliability_notes(
    source_type: SourceType,
    source_quality: SourceQuality,
    is_marketing_like: bool,
    marketing_signals: list[str],
    reliability_signals: list[str],
) -> str:
    parts = [f"source_type={source_type.value}", f"source_quality={source_quality.value}"]
    if is_marketing_like:
        parts.append("marketing_like=true")
    if marketing_signals:
        parts.append("signals=" + ",".join(marketing_signals))
    if reliability_signals:
        parts.append("reliability_signals=" + ",".join(reliability_signals))
    return "; ".join(parts)
