"""Heuristic counterevidence task builder."""

from __future__ import annotations

import re

from backend.app.providers.interfaces import VerificationTask
from backend.app.providers.source_packs import reliable_domains_for_market

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "行业",
    "市场",
    "用户",
    "来源",
}


class HeuristicCounterevidenceProvider:
    async def build_verification_tasks(
        self,
        claim_id: str,
        claim_text: str,
        market_scope: str,
    ) -> list[VerificationTask]:
        normalized = _normalize_claim_text(claim_text)
        if not normalized:
            return []

        scope_hint = _scope_hint(market_scope)
        corroborate_query = " ".join(part for part in [normalized, scope_hint, "官方 数据"] if part)
        challenge_query = " ".join(part for part in [normalized, scope_hint, "争议 风险 质疑"] if part)
        preferred_domains = reliable_domains_for_market(market_scope)

        return [
            VerificationTask(
                task_id=f"VT-{claim_id}-CORROBORATE",
                claim_id=claim_id,
                verification_goal="corroborate",
                query_variants=[corroborate_query, normalized],
                preferred_domains=preferred_domains,
                blocking=False,
            ),
            VerificationTask(
                task_id=f"VT-{claim_id}-CHALLENGE",
                claim_id=claim_id,
                verification_goal="challenge",
                query_variants=[challenge_query],
                preferred_domains=None,
                blocking=False,
            ),
        ]


def _normalize_claim_text(claim_text: str) -> str:
    collapsed = re.sub(r"\s+", " ", claim_text).strip()
    if not collapsed:
        return ""
    tokens = [token for token in re.split(r"[\s,.;:|/()\-]+", collapsed) if token]
    filtered = [token for token in tokens if token.lower() not in _STOPWORDS]
    shortened = " ".join(filtered[:12]).strip()
    return shortened or collapsed[:120]


def _scope_hint(market_scope: str) -> str:
    mapping = {
        "china": "中国",
        "global": "全球",
        "mixed": "中外",
        "custom": "",
    }
    return mapping.get(market_scope, "")
