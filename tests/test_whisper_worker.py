import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException


WORKER_PATH = Path(__file__).parents[1] / "apps" / "whisper-worker" / "app.py"
SPEC = importlib.util.spec_from_file_location("charvi_whisper_worker", WORKER_PATH)
assert SPEC is not None and SPEC.loader is not None
WORKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKER)


def test_whisper_worker_accepts_matching_internal_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHARVI_WHISPER_WORKER_TOKEN", "private-worker-token")
    assert WORKER.authorize_worker("private-worker-token") is None


def test_whisper_worker_rejects_invalid_internal_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHARVI_WHISPER_WORKER_TOKEN", "private-worker-token")
    with pytest.raises(HTTPException) as error:
        WORKER.authorize_worker("wrong-token")
    assert error.value.status_code == 401


def test_whisper_worker_fails_closed_without_configured_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CHARVI_WHISPER_WORKER_TOKEN", raising=False)
    with pytest.raises(HTTPException) as error:
        WORKER.authorize_worker("anything")
    assert error.value.status_code == 503
