"""Reconciliation of the measured and heard analyses."""

from __future__ import annotations

import pytest

from app.analysis import merger, spectral
from app.models.schemas import (
    ProcessingCategory,
    QualitativeAnalysis,
    QualitativeIssue,
    Severity,
    SourceDetection,
    SourceType,
)
from tests import synth

SOURCE = SourceDetection(
    source_type=SourceType.DRY_VOCAL,
    confidence=1.0,
    sub_bass_ratio=0.0,
    percussive_ratio=0.0,
    onset_rate_hz=1.0,
)


def features(signal):
    return spectral.analyze_samples(signal, synth.SR)


@pytest.fixture(scope="module")
def muddy_features():
    return features(synth.with_band_boost(synth.vocal(), 200.0, 500.0, 12.0))


def heard(*issues, summary="It sounds like a bedroom take."):
    return QualitativeAnalysis(
        summary=summary,
        tonal_balance="",
        room_sound="",
        dynamics="",
        artifacts="",
        issues=list(issues),
    )


def issue_named(profile, name):
    return next(issue for issue in profile.issues if issue.name == name)


def test_measurement_alone_produces_issues(muddy_features):
    profile = merger.merge(muddy_features, None, SOURCE)
    mud = issue_named(profile, "Low-Mid Buildup")
    assert mud.confidence == merger.CONFIDENCE_SPECTRAL_ONLY
    assert mud.sources == ["spectral"]
    assert mud.spectral_evidence["deviation_db"] > 0


def test_agreement_raises_confidence_and_takes_the_worse_severity(muddy_features):
    profile = merger.merge(
        muddy_features,
        heard(
            QualitativeIssue(
                name="Muddy low end",
                category=ProcessingCategory.EQ,
                severity=Severity.CRITICAL,
                description="Sounds muddy, like a blanket over the low mids.",
            )
        ),
        SOURCE,
    )
    mud = issue_named(profile, "Low-Mid Buildup")
    assert mud.confidence == merger.CONFIDENCE_AGREED
    assert mud.sources == ["spectral", "qualitative"]
    assert mud.severity is Severity.CRITICAL
    assert "Confirmed by ear" in mud.description
    assert not any(issue.name == "Muddy low end" for issue in profile.issues)


def test_unmatched_heard_issue_is_kept_at_lower_confidence(muddy_features):
    profile = merger.merge(
        muddy_features,
        heard(
            QualitativeIssue(
                name="Mouth clicks",
                category=ProcessingCategory.NOISE_REDUCTION,
                severity=Severity.MINOR,
                description="Audible clicks between words.",
            )
        ),
        SOURCE,
    )
    clicks = issue_named(profile, "Mouth clicks")
    assert clicks.confidence == merger.CONFIDENCE_QUALITATIVE_ONLY
    assert clicks.sources == ["qualitative"]
    assert clicks.spectral_evidence is None


def test_eq_issues_do_not_match_on_category_alone(muddy_features):
    """"Harsh" and "muddy" are both EQ problems, and are not the same problem."""
    profile = merger.merge(
        muddy_features,
        heard(
            QualitativeIssue(
                name="Harsh top end",
                category=ProcessingCategory.EQ,
                severity=Severity.MODERATE,
                description="The esses and consonants feel brittle up top.",
            )
        ),
        SOURCE,
    )
    assert issue_named(profile, "Low-Mid Buildup").sources == ["spectral"]
    assert issue_named(profile, "Harsh top end").sources == ["qualitative"]


def test_issues_are_ordered_worst_first(muddy_features):
    profile = merger.merge(muddy_features, None, SOURCE)
    order = [merger._SEVERITY_ORDER[issue.severity] for issue in profile.issues]
    assert order == sorted(order, reverse=True)


def test_clean_take_reports_few_issues():
    profile = merger.merge(features(synth.vocal()), None, SOURCE)
    assert all(issue.severity is not Severity.CRITICAL for issue in profile.issues)


def test_sibilance_becomes_a_de_ess_issue():
    sibilant = features(synth.with_sibilance(synth.vocal()))
    profile = merger.merge(sibilant, None, SOURCE)
    assert issue_named(profile, "Sibilance").category is ProcessingCategory.DE_ESS


def test_hum_becomes_a_noise_issue():
    hummed = features(synth.with_hum(synth.vocal(), freq=60.0))
    profile = merger.merge(hummed, None, SOURCE)
    hum = issue_named(profile, "Mains Hum")
    assert hum.category is ProcessingCategory.NOISE_REDUCTION
    assert hum.spectral_evidence["hum_freq_hz"] == 60.0


def test_summary_falls_back_to_measurements(muddy_features):
    profile = merger.merge(muddy_features, None, SOURCE)
    assert "no listening pass" in profile.qualitative_summary.lower()

    with_llm = merger.merge(muddy_features, heard(summary="Warm but cloudy."), SOURCE)
    assert with_llm.qualitative_summary == "Warm but cloudy."


def test_profile_carries_context(muddy_features):
    profile = merger.merge(
        muddy_features, None, SOURCE, genre="drill", notes=["separation skipped"]
    )
    assert profile.genre == "drill"
    assert profile.analysis_notes == ["separation skipped"]
    assert profile.source.source_type is SourceType.DRY_VOCAL
