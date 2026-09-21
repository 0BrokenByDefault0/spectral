"""The listening pass's prompt building and response handling.

Nothing here calls the API — these cover the parts that can go wrong without it.
"""

from __future__ import annotations

import json

import pytest

from app.analysis import qualitative
from app.models.schemas import ProcessingCategory, Severity

VALID = {
    "summary": "Bedroom take, usable.",
    "tonal_balance": "Muddy around 300 Hz.",
    "room_sound": "Small untreated room.",
    "dynamics": "Fairly even.",
    "artifacts": "Two plosives.",
    "genre_context": "Fine for lo-fi rap.",
    "issues": [
        {
            "name": "Mud",
            "category": "EQ",
            "severity": "MODERATE",
            "description": "Cloudy low mids.",
        }
    ],
}


def test_parses_a_valid_response():
    result = qualitative.parse_response(json.dumps(VALID))
    assert result.summary == "Bedroom take, usable."
    assert result.issues[0].category is ProcessingCategory.EQ
    assert result.issues[0].severity is Severity.MODERATE


def test_issues_may_be_absent():
    minimal = {k: v for k, v in VALID.items() if k != "issues"}
    assert qualitative.parse_response(json.dumps(minimal)).issues == []


@pytest.mark.parametrize(
    "text",
    ["", None, "not json at all", json.dumps({"summary": "missing the rest"})],
)
def test_bad_responses_are_reported_not_raised_raw(text):
    with pytest.raises(qualitative.QualitativeUnavailableError):
        qualitative.parse_response(text)


def test_unknown_category_is_rejected():
    bad = json.loads(json.dumps(VALID))
    bad["issues"][0]["category"] = "VIBES"
    with pytest.raises(qualitative.QualitativeUnavailableError):
        qualitative.parse_response(json.dumps(bad))


def test_prompt_mentions_genre_when_given():
    assert "drill" in qualitative.build_prompt("drill", extracted_vocal=False)
    assert "drill" not in qualitative.build_prompt(None, extracted_vocal=False)


def test_prompt_warns_about_separation_artifacts():
    prompt = qualitative.build_prompt(None, extracted_vocal=True)
    assert "extracted from a full mix" in prompt
    assert "extracted from a full mix" not in qualitative.build_prompt(None, False)


def test_missing_api_key_is_a_clean_failure(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(qualitative.QualitativeUnavailableError, match="GEMINI_API_KEY"):
        qualitative.analyze(tmp_path / "nothing.wav")
