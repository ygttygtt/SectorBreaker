"""Source coverage metrics for talent-demand evidence."""

from __future__ import annotations

from backend.app.schemas.evidence import EvidenceItem, SourceChannel, SourceQuality, VerificationStatus
from backend.app.talent_demand.models import JobPostingSignal, SourceCoverageMatrix


def build_source_coverage_matrix(
    evidence: list[EvidenceItem],
    postings: list[JobPostingSignal],
    *,
    min_posting_sample: int = 3,
) -> SourceCoverageMatrix:
    channel_counts = _count_channels(evidence)
    salary_signal_count = sum(1 for posting in postings if posting.salary_text)
    experience_signal_count = sum(1 for posting in postings if posting.experience_text)
    skill_signal_count = sum(1 for posting in postings if posting.skills or posting.tools)
    weak_or_unverified_count = sum(1 for item in evidence if _is_weak_or_unverified(item))

    matrix = SourceCoverageMatrix(
        total_evidence=len(evidence),
        uploaded_jd_count=channel_counts.get(SourceChannel.USER_UPLOAD, 0),
        uploaded_report_count=channel_counts.get(SourceChannel.ASSISTANT_BRIEF, 0),
        search_result_count=channel_counts.get(SourceChannel.SEARCH, 0),
        extracted_page_count=channel_counts.get(SourceChannel.RELIABLE_PROVIDER, 0),
        occupation_standard_count=channel_counts.get(SourceChannel.SYSTEM, 0),
        salary_signal_count=salary_signal_count,
        experience_signal_count=experience_signal_count,
        skill_signal_count=skill_signal_count,
        weak_or_unverified_count=weak_or_unverified_count,
    )
    matrix.gaps = _build_gaps(matrix, postings, min_posting_sample)
    return matrix


def _count_channels(evidence: list[EvidenceItem]) -> dict[SourceChannel, int]:
    counts: dict[SourceChannel, int] = {}
    for item in evidence:
        counts[item.source_channel] = counts.get(item.source_channel, 0) + 1
    return counts


def _is_weak_or_unverified(item: EvidenceItem) -> bool:
    return (
        item.verification_status in {VerificationStatus.UNVERIFIED, VerificationStatus.CONFLICTING}
        or item.source_quality in {SourceQuality.LOW, SourceQuality.UNKNOWN}
    )


def _build_gaps(
    matrix: SourceCoverageMatrix,
    postings: list[JobPostingSignal],
    min_posting_sample: int,
) -> list[str]:
    gaps: list[str] = []
    if len(postings) < min_posting_sample:
        gaps.append("low_sample")
    if matrix.salary_signal_count == 0:
        gaps.append("no_salary_signal")
    if matrix.experience_signal_count == 0:
        gaps.append("no_experience_signal")
    if matrix.search_result_count > 0 and (
        matrix.uploaded_jd_count
        + matrix.uploaded_report_count
        + matrix.extracted_page_count
        + matrix.occupation_standard_count
        == 0
    ):
        gaps.append("search_only_evidence")
    return gaps
