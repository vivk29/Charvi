from __future__ import annotations

import hmac
import mimetypes
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

MAX_AUDIO_BYTES = 20 * 1024 * 1024
ALLOWED_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/aac",
    "audio/flac",
}
EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/flac": ".flac",
}


class TranscriptionResult(BaseModel):
    text: str
    language: str | None
    language_probability: float | None
    duration_seconds: float | None


@asynccontextmanager
async def lifespan(app: FastAPI):
    from faster_whisper import WhisperModel

    model_size = os.getenv("WHISPER_MODEL_SIZE", "tiny")
    device = os.getenv("WHISPER_DEVICE", "cpu")
    compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    cpu_threads = int(os.getenv("WHISPER_CPU_THREADS", "4"))
    download_root = os.getenv("WHISPER_DOWNLOAD_ROOT", "/models")
    app.state.model = WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
        cpu_threads=cpu_threads,
        download_root=download_root,
    )
    yield
    app.state.model = None


app = FastAPI(title="Charvi Private Whisper Worker", version="0.1.0", lifespan=lifespan)


def authorize_worker(token: str | None) -> None:
    expected = os.getenv("CHARVI_WHISPER_WORKER_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Worker authentication is not configured.")
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid worker token.")


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "model_ready": getattr(app.state, "model", None) is not None,
        "model": os.getenv("WHISPER_MODEL_SIZE", "tiny"),
    }


@app.post("/v1/transcribe", response_model=TranscriptionResult)
async def transcribe(
    file: Annotated[UploadFile, File()],
    language: Annotated[str | None, Form()] = None,
    worker_token: Annotated[str | None, Header(alias="X-Charvi-Worker-Token")] = None,
) -> TranscriptionResult:
    authorize_worker(worker_token)
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported audio format.")
    content = await file.read(MAX_AUDIO_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="The audio recording is empty.")
    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio must be 20 MB or smaller.")

    suffix = EXTENSIONS.get(file.content_type) or mimetypes.guess_extension(file.content_type) or ".audio"
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
            temporary.write(content)
            temp_path = temporary.name

        model = getattr(app.state, "model", None)
        if model is None:
            raise HTTPException(status_code=503, detail="Speech model is not ready.")
        segments, info = model.transcribe(
            temp_path,
            language=language or None,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        completed = list(segments)
        transcript = " ".join(segment.text.strip() for segment in completed).strip()
        return TranscriptionResult(
            text=transcript,
            language=getattr(info, "language", None),
            language_probability=getattr(info, "language_probability", None),
            duration_seconds=getattr(info, "duration", None),
        )
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
        await file.close()
