from backend.app.schemas.evidence import (
    EvidenceItem,
    SourceChannel,
    SourceQuality,
    VerificationStatus,
)
from backend.app.talent_demand.models import JobPostingSignal
from backend.app.talent_demand.source_coverage import build_source_coverage_matrix


def _evidence(
    evidence_id: str,
    channel: SourceChannel,
    verification_status: VerificationStatus = VerificationStatus.PARTIALLY_VERIFIED,
) -> EvidenceItem:
    return EvidenceItem(
        id=evidence_id,
        project_id="project-1",
        source_title=evidence_id,
        snippet="岗位需求样本",
        source_channel=channel,
        source_quality=SourceQuality.MEDIUM,
        confidence=0.6,
        verification_status=verification_status,
    )


def test_source_coverage_counts_evidence_channels_and_posting_signals() -> None:
    evidence = [
        _evidence("EV-JD-1", SourceChannel.USER_UPLOAD),
        _evidence("EV-REPORT-1", SourceChannel.ASSISTANT_BRIEF, VerificationStatus.UNVERIFIED),
        _evidence("EV-BOSS-1", SourceChannel.BOSS_JOB),
        _evidence("EV-SEARCH-1", SourceChannel.SEARCH),
        _evidence("EV-STANDARD-1", SourceChannel.SYSTEM),
    ]
    postings = [
        JobPostingSignal(
            title="大模型应用开发工程师",
            salary_text="20-35K",
            experience_text="3-5年",
            skills=["Python"],
            evidence_ids=["EV-JD-1"],
        ),
        JobPostingSignal(title="AI Agent 工程师", skills=["Agent"], evidence_ids=["EV-SEARCH-1"]),
    ]

    coverage = build_source_coverage_matrix(evidence, postings, min_posting_sample=2)

    assert coverage.total_evidence == 5
    assert coverage.uploaded_jd_count == 1
    assert coverage.uploaded_report_count == 1
    assert coverage.boss_job_count == 1
    assert coverage.search_result_count == 1
    assert coverage.occupation_standard_count == 1
    assert coverage.salary_signal_count == 1
    assert coverage.experience_signal_count == 1
    assert coverage.skill_signal_count == 2
    assert coverage.weak_or_unverified_count == 1
    assert coverage.gaps == []


def test_source_coverage_reports_low_sample_and_search_only_gaps() -> None:
    evidence = [_evidence("EV-SEARCH-1", SourceChannel.SEARCH)]
    postings = [JobPostingSignal(title="AI 工程师", evidence_ids=["EV-SEARCH-1"])]

    coverage = build_source_coverage_matrix(evidence, postings, min_posting_sample=3)

    assert "low_sample" in coverage.gaps
    assert "no_salary_signal" in coverage.gaps
    assert "no_experience_signal" in coverage.gaps
    assert "search_only_evidence" in coverage.gaps
