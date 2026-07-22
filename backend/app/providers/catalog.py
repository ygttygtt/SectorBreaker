"""Non-secret onboarding metadata for optional external providers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderOnboarding:
    key: str
    display_name: str
    capability: str
    signup_url: str | None
    pricing_url: str | None
    requires_api_key: bool
    free_tier_summary: str


PROVIDER_ONBOARDING: tuple[ProviderOnboarding, ...] = (
    ProviderOnboarding(
        key="tavily",
        display_name="Tavily",
        capability="search",
        signup_url="https://app.tavily.com/home",
        pricing_url="https://docs.tavily.com/documentation/api-credits",
        requires_api_key=True,
        free_tier_summary="官方当前提供每月免费 credits；超额后按所选套餐计费。",
    ),
    ProviderOnboarding(
        key="serper",
        display_name="Serper",
        capability="search",
        signup_url="https://serper.dev/signup",
        pricing_url="https://serper.dev/",
        requires_api_key=True,
        free_tier_summary="可免费注册；官方长期方案以充值 credits 为主。",
    ),
    ProviderOnboarding(
        key="brave",
        display_name="Brave Search",
        capability="search",
        signup_url="https://api.search.brave.com/app/keys",
        pricing_url="https://api.search.brave.com/app/plans",
        requires_api_key=True,
        free_tier_summary="是否有免费额度及限速以官方控制台当前方案为准。",
    ),
    ProviderOnboarding(
        key="exa",
        display_name="Exa",
        capability="search",
        signup_url="https://dashboard.exa.ai/api-keys",
        pricing_url="https://exa.ai/pricing",
        requires_api_key=True,
        free_tier_summary="官方当前提供新用户试用 credits；后续按用量计费。",
    ),
    ProviderOnboarding(
        key="firecrawl",
        display_name="Firecrawl",
        capability="search_and_extraction",
        signup_url="https://www.firecrawl.dev/app/api-keys",
        pricing_url="https://www.firecrawl.dev/pricing",
        requires_api_key=True,
        free_tier_summary="官方当前提供每月免费 credits；搜索和抓取都会消耗额度。",
    ),
    ProviderOnboarding(
        key="http",
        display_name="本地 HTTP 抽取",
        capability="extraction",
        signup_url=None,
        pricing_url=None,
        requires_api_key=False,
        free_tier_summary="本地执行且无需 API Key，但不负责浏览器渲染和反爬绕过。",
    ),
    ProviderOnboarding(
        key="jina",
        display_name="Jina Reader",
        capability="extraction",
        signup_url="https://jina.ai/reader",
        pricing_url="https://jina.ai/reader",
        requires_api_key=False,
        free_tier_summary="无 Key 可低速使用 Reader；更高额度按官方 token 方案。",
    ),
)
