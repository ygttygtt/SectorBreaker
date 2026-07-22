import asyncio

from backend.app.providers.source_verification import HeuristicSourceVerificationProvider
from backend.app.schemas import SourcePolicy


def test_source_verifier_marks_government_source_as_high_quality() -> None:
    provider = HeuristicSourceVerificationProvider()

    result = asyncio.run(
        provider.assess_source(
            url="https://www.stats.gov.cn/sj/zxfb/202401/t20240101_123.html",
            title="国家统计公报",
            snippet="官方数据发布。",
            extracted_text=None,
            source_policy=SourcePolicy.RELIABLE_ONLY.value,
        )
    )

    assert result.source_type == "government"
    assert result.source_quality == "high"
    assert result.recommended_verification_status == "partially_verified"
    assert "source_pack" in (result.reliability_notes or "")


def test_source_verifier_marks_marketing_blog_as_unverified() -> None:
    provider = HeuristicSourceVerificationProvider()

    result = asyncio.run(
        provider.assess_source(
            url="https://example.com/blog/best-ai-tools-2026",
            title="Best AI Tools 2026",
            snippet="Book demo now and start free trial.",
            extracted_text=None,
            source_policy=SourcePolicy.RELIABLE_FIRST.value,
        )
    )

    assert result.is_marketing_like is True
    assert result.recommended_verification_status == "unverified"


def test_source_verifier_marks_disclosure_source_as_high_quality() -> None:
    provider = HeuristicSourceVerificationProvider()

    result = asyncio.run(
        provider.assess_source(
            url="https://www.cninfo.com.cn/new/disclosure/detail",
            title="上市公司公告",
            snippet="年度报告与经营数据披露。",
            extracted_text=None,
            source_policy=SourcePolicy.RELIABLE_ONLY.value,
        )
    )

    assert result.source_type == "company_disclosure"
    assert result.source_quality == "high"
    assert result.is_original_source is True
    assert result.recommended_verification_status == "partially_verified"
