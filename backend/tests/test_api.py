"""The HTTP surface: the envelope, the guards, and a real analysis round trip."""

from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.api.analyze import MAX_UPLOAD_BYTES
from app.main import app
from app.models.schemas import AnalysisResult
from tests import synth


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def wav_bytes(signal, sr=synth.SR):
    buffer = io.BytesIO()
    sf.write(buffer, signal, sr, format="WAV")
    return buffer.getvalue()


def upload(client, signal=None, name="take.wav", data=None, raw=None):
    payload = raw if raw is not None else wav_bytes(signal)
    return client.post(
        "/analyze",
        files={"file": (name, payload, "audio/wav")},
        data=data or {"use_llm": "false"},
    )


def test_health_uses_the_envelope(client):
    body = client.get("/health").json()
    assert body == {"status": "ok", "data": {"status": "healthy"}}


def test_analysis_round_trip(client):
    response = upload(client, synth.with_sibilance(synth.vocal()))
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"

    result = AnalysisResult.model_validate(body["data"])
    assert result.profile.issues
    assert [chain.tier.value for chain in result.chains] == ["FREE", "MID", "PREMIUM"]
    assert all(chain.steps for chain in result.chains)


def test_genre_is_carried_into_the_profile(client):
    response = upload(client, synth.vocal(), data={"use_llm": "false", "genre": "drill"})
    assert response.json()["data"]["profile"]["genre"] == "drill"


def test_an_unsupported_format_is_refused(client):
    response = upload(client, synth.vocal(), name="take.txt")
    assert response.status_code == 415
    assert response.json()["status"] == "error"
    assert ".txt is not supported" in response.json()["message"]


def test_a_clip_that_is_too_short_is_refused(client):
    response = upload(client, np.zeros(int(0.3 * synth.SR), dtype=np.float32))
    assert response.status_code == 422
    assert "at least 1.0s" in response.json()["message"]


def test_an_empty_upload_is_refused(client):
    response = upload(client, raw=b"", name="take.wav")
    assert response.status_code == 422
    assert "empty" in response.json()["message"]


def test_unreadable_audio_is_refused(client):
    response = upload(client, raw=b"not a wav file at all" * 100, name="take.wav")
    assert response.status_code == 422
    assert response.json()["status"] == "error"


def test_an_oversized_upload_is_refused(client):
    response = upload(client, raw=b"\0" * (MAX_UPLOAD_BYTES + 1), name="big.wav")
    assert response.status_code == 413
    assert "larger than" in response.json()["message"]


def test_a_missing_file_is_reported_in_the_envelope(client):
    response = client.post("/analyze", data={"use_llm": "false"})
    assert response.status_code == 422
    assert response.json()["status"] == "error"
    assert "file" in response.json()["message"]


def test_unknown_routes_stay_in_the_envelope(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.json()["status"] == "error"


def test_tiers_are_published_for_the_ui(client):
    assert client.get("/tiers").json()["data"]["tiers"] == ["FREE", "MID", "PREMIUM"]


def test_cors_allows_the_frontend(client):
    response = client.options(
        "/analyze",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
