"""Separation wiring: when it runs, when it does not, and what the profile says.

Demucs itself is not exercised here — a real separation is minutes of CPU. What matters
for correctness is the branching around it and that the profile always explains which
audio was actually measured.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import soundfile as sf

from app.analysis import pipeline
from app.analysis.pipeline import analyze_file
from app.models.schemas import SourceType
from app.separation import demucs_runner
from tests import synth


def write(tmp_path: Path, signal, name: str) -> Path:
    path = tmp_path / name
    sf.write(path, signal, synth.SR)
    return path


@pytest.fixture
def mix(tmp_path):
    return write(tmp_path, synth.full_mix(), "mix.wav")


def test_a_missing_file_is_reported(tmp_path):
    with pytest.raises(demucs_runner.SeparationError, match="no such file"):
        demucs_runner.separate_vocal(tmp_path / "gone.wav")


def test_a_dry_vocal_is_never_separated(tmp_path, monkeypatch):
    """Separating a clean take degrades it for nothing, so it must not be attempted."""
    called = False

    def explode(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("separation ran on a dry vocal")

    monkeypatch.setattr(demucs_runner, "separate_vocal", explode)
    profile = analyze_file(write(tmp_path, synth.vocal(), "take.wav"), use_llm=False)

    assert not called
    assert profile.source.source_type is SourceType.DRY_VOCAL


def test_separation_can_be_turned_off(mix):
    profile = analyze_file(mix, use_llm=False, separate=False)
    note = " ".join(profile.analysis_notes)
    assert "separation was turned off" in note
    assert "include the instrumental" in note


def test_a_missing_demucs_is_explained(mix, monkeypatch):
    monkeypatch.setattr(demucs_runner, "available", lambda: False)
    profile = analyze_file(mix, use_llm=False)
    assert "not installed" in " ".join(profile.analysis_notes)


def test_a_failed_separation_falls_back_to_the_mix(mix, monkeypatch):
    monkeypatch.setattr(demucs_runner, "available", lambda: True)
    monkeypatch.setattr(
        demucs_runner,
        "separate_vocal",
        lambda *a, **k: (_ for _ in ()).throw(demucs_runner.SeparationError("out of memory")),
    )
    profile = analyze_file(mix, use_llm=False)

    note = " ".join(profile.analysis_notes)
    assert "separation failed (out of memory)" in note
    assert "include the instrumental" in note
    assert profile.issues  # the mix is still analysed rather than the request failing


def test_a_successful_separation_analyses_the_stem(tmp_path, mix, monkeypatch):
    """The profile must describe the stem, and say so."""
    stem = write(tmp_path, synth.vocal(), "vocals.wav")
    separated = demucs_runner.Separated(vocal_path=stem, model="htdemucs", seconds=12.0)

    monkeypatch.setattr(demucs_runner, "available", lambda: True)
    monkeypatch.setattr(demucs_runner, "separate_vocal", lambda *a, **k: separated)
    cleaned: list[demucs_runner.Separated] = []
    monkeypatch.setattr(demucs_runner, "cleanup", cleaned.append)

    profile = analyze_file(mix, use_llm=False)

    note = " ".join(profile.analysis_notes)
    assert "vocal was isolated with htdemucs" in note
    assert "separation artifacts" in note
    # Detection still reports what was uploaded, not what was measured.
    assert profile.source.source_type is SourceType.FULL_MIX
    assert cleaned == [separated]


def test_the_listening_pass_is_told_the_vocal_was_extracted(tmp_path, mix, monkeypatch):
    stem = write(tmp_path, synth.vocal(), "vocals.wav")
    separated = demucs_runner.Separated(vocal_path=stem, model="htdemucs", seconds=1.0)
    monkeypatch.setattr(demucs_runner, "available", lambda: True)
    monkeypatch.setattr(demucs_runner, "separate_vocal", lambda *a, **k: separated)
    monkeypatch.setattr(demucs_runner, "cleanup", lambda _: None)

    seen: dict = {}

    def record(path, genre=None, extracted_vocal=False):
        seen.update(path=path, extracted_vocal=extracted_vocal)
        raise pipeline.qualitative.QualitativeUnavailableError("no key")

    monkeypatch.setattr(pipeline.qualitative, "analyze", record)
    analyze_file(mix, use_llm=True)

    assert seen["extracted_vocal"] is True
    assert seen["path"] == str(stem)


def test_cleanup_removes_the_working_directory(tmp_path):
    holding = tmp_path / "holding"
    stem = holding / "htdemucs" / "track" / "vocals.wav"
    stem.parent.mkdir(parents=True)
    stem.write_bytes(b"")

    demucs_runner.cleanup(
        demucs_runner.Separated(vocal_path=stem, model="htdemucs", seconds=1.0)
    )
    assert not holding.exists()
