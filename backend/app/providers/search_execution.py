"""Budget-aware typed execution for SearchProvider implementations."""

from __future__ import annotations

import re
import time

from backend.app.providers.interfaces import ProviderOutcome, SearchProvider, SearchQuery, SearchResponse

_SECRET_PATTERN = re.compile(r"(?i)(?:sk|fc|tvly)-[a-z0-9_-]{12,}|[a-f0-9]{32,}")


async def execute_search(
    provider: SearchProvider,
    query: SearchQuery,
    *,
    request_budget: int | None = None,
) -> SearchResponse:
    if request_budget is not None and request_budget <= 0:
        return SearchResponse(
            results=[],
            provider_outcomes=[ProviderOutcome(provider_id=search_provider_id(provider), status="skipped_budget")],
            request_count=0,
        )
    diagnostic_search = getattr(provider, "search_with_diagnostics", None)
    max_requests = getattr(provider, "max_requests_per_search", None)
    if callable(diagnostic_search) and isinstance(max_requests, int) and max_requests >= 1:
        dispatch_budget = max_requests if request_budget is None else min(max_requests, request_budget)
        started = time.perf_counter()
        try:
            response = await diagnostic_search(query, request_budget=dispatch_budget)
        except Exception as exc:
            return SearchResponse(
                results=[],
                provider_outcomes=[ProviderOutcome(
                    provider_id=search_provider_id(provider),
                    status="timeout" if "timeout" in type(exc).__name__.lower() else "error",
                    latency_ms=_elapsed_ms(started),
                    error_code=type(exc).__name__,
                    error_message=_safe_error_message(exc),
                )],
                request_count=dispatch_budget,
            )
        if not isinstance(response, SearchResponse) or not 0 <= response.request_count <= dispatch_budget:
            return SearchResponse(
                results=[],
                provider_outcomes=[ProviderOutcome(
                    provider_id=search_provider_id(provider),
                    status="error",
                    latency_ms=_elapsed_ms(started),
                    error_code="InvalidSearchDiagnostics",
                    error_message="provider returned invalid request accounting",
                )],
                request_count=dispatch_budget,
            )
        return response

    provider_id = search_provider_id(provider)
    started = time.perf_counter()
    try:
        results = await provider.search(query)
    except Exception as exc:
        return SearchResponse(
            results=[],
            provider_outcomes=[ProviderOutcome(
                provider_id=provider_id,
                status="timeout" if "timeout" in type(exc).__name__.lower() else "error",
                latency_ms=_elapsed_ms(started),
                error_code=type(exc).__name__,
                error_message=_safe_error_message(exc),
            )],
            request_count=1,
        )
    return SearchResponse(
        results=results,
        provider_outcomes=[ProviderOutcome(
            provider_id=provider_id,
            status="ok" if results else "empty",
            latency_ms=_elapsed_ms(started),
            result_count=len(results),
        )],
        request_count=1,
    )


def search_provider_id(provider: object) -> str:
    return type(provider).__name__.removesuffix("SearchProvider").lower() or "search"


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _safe_error_message(exc: Exception) -> str:
    message = _SECRET_PATTERN.sub("[redacted]", str(exc).replace("\n", " "))
    return message[:200]
