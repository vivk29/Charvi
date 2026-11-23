from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from charvi_api.main import VoiceSynthesisInput, app


@pytest.mark.parametrize(
    "voice",
    ["af_heart", "af_bella", "af_nicole", "bf_emma", "hf_alpha", "hf_beta"],
)
def test_supported_feminine_voice_ids(voice: str) -> None:
    request = VoiceSynthesisInput(text="Hello from Charvi", voice=voice)
    assert request.voice == voice


def test_masculine_or_unknown_voice_id_is_not_accepted() -> None:
    with pytest.raises(ValidationError):
        VoiceSynthesisInput(text="Hello from Charvi", voice="am_adam")


def test_voice_endpoint_requires_authenticated_owner() -> None:
    response = TestClient(app).post(
        "/v1/voice/speak",
        json={"text": "Hello from Charvi", "voice": "af_heart"},
    )
    assert response.status_code == 401
