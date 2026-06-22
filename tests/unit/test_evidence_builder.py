from backend.app.evidence_builder import citation_to_evidence
from backend.app.providers.interfaces import SourceAssessment
from backend.app.schemas import SourceQuality, VerificationStatus
from backend.app.schemas.documents import DocumentCitation, ProjectDocument


def test_citation_to_evidence_marks_marketing_source_for_counterevidence() -> None:
    document = ProjectDocument(
        id="doc-1",
        project_id="project-1",
        channel="assistant_brief",
        file_name="report.md",
        mime_type="text/markdown",
        content="report",
    )
    citation = DocumentCitation(
        id="cit-1",
        document_id="doc-1",
        raw_reference="https://example.com/blog/best-ai-tools-2026",
        source_url="https://example.com/blog/best-ai-tools-2026",
        referenced_segment_ids=["doc-1-seg-001"],
    )
    assessment = SourceAssessment(
        source_type="web",
        source_quality="low",
        is_original_source=False,
        is_marketing_like=True,
        url=citation.source_url,
        domain="example.com",
        marketing_signals=["marketing_like_url_pattern"],
        reliability_notes="marketing_like=true",
        recommended_verification_status="unverified",
    )

    evidence = citation_to_evidence(
        project_id="project-1",
        document=document,
        citation=citation,
        assessment=assessment,
        evidence_index=1,
    )

    assert evidence.needs_counterevidence is True
    assert evidence.source_quality == SourceQuality.LOW
    assert evidence.verification_status == VerificationStatus.UNVERIFIED


def test_citation_to_evidence_preserves_verified_source_with_url() -> None:
    document = ProjectDocument(
        id="doc-2",
        project_id="project-1",
        channel="assistant_brief",
        file_name="report.md",
        mime_type="text/markdown",
        content="report",
    )
    citation = DocumentCitation(
        id="cit-2",
        document_id="doc-2",
        raw_reference="https://www.stats.gov.cn/report",
        source_url="https://www.stats.gov.cn/report",
        referenced_segment_ids=["doc-2-seg-001"],
    )
    assessment = SourceAssessment(
        source_type="government",
        source_quality="high",
        is_original_source=True,
        is_marketing_like=False,
        url=citation.source_url,
        domain="www.stats.gov.cn",
        marketing_signals=[],
        reliability_notes="source_quality=high",
        recommended_verification_status="verified",
    )

    evidence = citation_to_evidence(
        project_id="project-1",
        document=document,
        citation=citation,
        assessment=assessment,
        evidence_index=1,
    )

    assert evidence.source_url == "https://www.stats.gov.cn/report"
    assert evidence.verification_status == VerificationStatus.VERIFIED
