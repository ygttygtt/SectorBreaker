"""Smoke test for the configured search + extraction stack."""

from __future__ import annotations

import asyncio
import json
import os
import sys

from backend.app.env import load_local_env
from backend.app.providers.factory import build_content_extraction_provider, build_search_provider
from backend.app.providers.interfaces import SearchQuery
from backend.app.providers.source_policy import search_constraints_for_policy
from backend.app.providers.source_verification import HeuristicSourceVerificationProvider


def _print_human_summary(payload: dict[str, object]) -> None:
    print(f"source_policy: {payload.get('source_policy')}")
    providers = payload.get("search_provider")
    extraction_provider = payload.get("extraction_provider")
    result_count = payload.get("result_count")
    print(f"search_provider: {providers}")
    print(f"extraction_provider: {extraction_provider}")
    print(f"allowed_domains: {payload.get('allowed_domains')}")
    print(f"blocked_domains: {payload.get('blocked_domains')}")
    print(f"result_count: {result_count}")

    if "first_result_assessment" in payload:
        assessment = payload["first_result_assessment"]
        if isinstance(assessment, dict):
            print("first_result_source_quality:", assessment.get("source_quality"))
            print("first_result_verification_status:", assessment.get("recommended_verification_status"))

    if payload.get("results"):
        first_result = payload["results"][0]
        if isinstance(first_result, dict):
            print("first_result_title:", first_result.get("title"))
            print("first_result_url:", first_result.get("url"))


async def main() -> int:
    load_local_env()

    search_provider = build_search_provider()
    extraction_provider = build_content_extraction_provider()
    source_verifier = HeuristicSourceVerificationProvider()

    if search_provider is None:
        print("No search provider configured. Fill .env first.", file=sys.stderr)
        return 1

    query = os.getenv("SECTORBREAKER_SMOKE_QUERY", "AI agent market map")
    market_scope = os.getenv("SECTORBREAKER_SMOKE_SCOPE", "mixed")
    source_policy = os.getenv("SECTORBREAKER_SMOKE_SOURCE_POLICY", "open_web")
    allowed_domains = [
        item.strip()
        for item in os.getenv("SECTORBREAKER_SMOKE_ALLOWED_DOMAINS", "").split(",")
        if item.strip()
    ]
    blocked_domains = [
        item.strip()
        for item in os.getenv("SECTORBREAKER_SMOKE_BLOCKED_DOMAINS", "").split(",")
        if item.strip()
    ]
    policy_allowed_domains, policy_blocked_domains = search_constraints_for_policy(
        {
            "market_scope": market_scope,
            "source_policy": source_policy,
        },
        verification=True,
        preferred_domains=allowed_domains,
    )
    effective_allowed_domains = allowed_domains or policy_allowed_domains
    effective_blocked_domains = list(dict.fromkeys(blocked_domains + policy_blocked_domains))

    results = await search_provider.search(
        SearchQuery(
            query=query,
            market_scope=market_scope,
            max_results=3,
            allowed_domains=effective_allowed_domains,
            blocked_domains=effective_blocked_domains,
        )
    )

    payload: dict[str, object] = {
        "query": query,
        "market_scope": market_scope,
        "source_policy": source_policy,
        "search_provider": type(search_provider).__name__,
        "extraction_provider": type(extraction_provider).__name__,
        "allowed_domains": effective_allowed_domains,
        "blocked_domains": effective_blocked_domains,
        "result_count": len(results),
        "results": [
            {
                "title": item.title,
                "url": item.url,
                "snippet": item.snippet,
                "published_date": item.published_date,
            }
            for item in results
        ],
    }

    if results:
        first = results[0]
        page = await extraction_provider.extract_url(first.url)
        assessment = await source_verifier.assess_source(
            url=page.canonical_url or page.url,
            title=page.title or first.title,
            snippet=first.snippet,
            extracted_text=page.raw_text,
            source_policy=source_policy,
        )
        payload["first_result_extraction"] = {
            "title": page.title,
            "domain": page.domain,
            "extraction_provider": page.extraction_provider,
            "raw_text_preview": page.raw_text[:500],
        }
        payload["first_result_assessment"] = {
            "source_type": assessment.source_type,
            "source_quality": assessment.source_quality,
            "is_original_source": assessment.is_original_source,
            "is_marketing_like": assessment.is_marketing_like,
            "recommended_verification_status": assessment.recommended_verification_status,
            "reliability_notes": assessment.reliability_notes,
        }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    _print_human_summary(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
