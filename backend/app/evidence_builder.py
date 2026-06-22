"""Convert document citations and source assessments into evidence items."""

from __future__ import annotations

from backend.app.providers.interfaces import SourceAssessment
from backend.app.schemas import (
    ClaimStrength,
    ClaimType,
    EvidenceClaim,
    EvidenceItem,
    SourceChannel,
    SourceQuality,
    VerificationStatus,
)
from backend.app.schemas.documents import DocumentCitation, ProjectDocument


def citation_to_evidence(
    *,
    project_id: str,
    document: ProjectDocument,
    citation: DocumentCitation,
    assessment: SourceAssessment,
    evidence_index: int,
) -> EvidenceItem:
    verification_status = VerificationStatus(assessment.recommended_verification_status or VerificationStatus.UNVERIFIED.value)
    source_quality = SourceQuality(assessment.source_quality or SourceQuality.UNKNOWN.value)
    needs_counterevidence = (
        assessment.is_marketing_like
        or verification_status == VerificationStatus.UNVERIFIED
        or source_quality in {SourceQuality.LOW, SourceQuality.UNKNOWN}
    )
    claim_strength = ClaimStrength.MARKETING if assessment.is_marketing_like else ClaimStrength.OPINION
    evidence_id = f"EV-DOC-{document.id}-{evidence_index:03d}"
    reliability_notes = assessment.reliability_notes or ""
    if assessment.marketing_signals:
        reliability_notes = (reliability_notes + "; " if reliability_notes else "") + "signals=" + ",".join(assessment.marketing_signals)

    return EvidenceItem(
        id=evidence_id,
        project_id=project_id,
        source_title=citation.source_title or citation.source_url or citation.raw_reference,
        source_url=citation.source_url,
        source_type=assessment.source_type,
        source_channel=SourceChannel.ASSISTANT_BRIEF if document.channel == "assistant_brief" else SourceChannel.USER_UPLOAD,
        source_policy=None,
        raw_excerpt=citation.raw_reference,
        snippet=citation.raw_reference,
        summary=f"Document citation extracted from {document.file_name or document.id}",
        claims=[
            EvidenceClaim(
                claim_id=f"CL-{evidence_id}",
                text=citation.raw_reference,
                claim_type=ClaimType.GENERAL_FACT,
                support_level=0.4 if verification_status == VerificationStatus.VERIFIED else 0.2,
                requires_verification=verification_status != VerificationStatus.VERIFIED,
                verification_status=verification_status,
                evidence_ids=[evidence_id],
                notes=reliability_notes or None,
            )
        ],
        source_quality=source_quality,
        claim_strength=claim_strength,
        bias_risk=reliability_notes or None,
        needs_counterevidence=needs_counterevidence,
        collected_by="document_citation_ingestion",
        confidence=0.8 if verification_status == VerificationStatus.VERIFIED else 0.45,
        verification_status=verification_status,
    )
