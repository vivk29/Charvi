# Charvi private Whisper worker

This optional worker provides self-hosted speech-to-text for dashboard voice recordings.

- Uses faster-whisper with the multilingual `tiny` model by default.
- Defaults to CPU + INT8 so it does not require an NVIDIA GPU.
- Supports language hints for English (`en`), Hindi (`hi`) and Kannada (`kn`), plus Whisper's automatic language detection when omitted.
- Accepts audio up to 20 MB in WebM, Ogg, WAV, MP3, MP4/AAC or FLAC.
- Keeps uploaded audio in a temporary file only while the request is processed and deletes it afterwards.
- Requires a shared worker token; never exposes the worker port to the host.
- Model files persist in the named `whisper-model-cache` Docker volume.

The tiny model is the selected baseline for a 4 GB RAM laptop without an NVIDIA GPU. It runs on CPU with INT8 and two CPU threads. The Compose worker is capped at 1 GB RAM and 1.5 CPUs. This is a best-effort local configuration, not a promise of real-time transcription; long recordings may be slow or hit the memory cap. Keep the Browser Use and Kokoro workers off on this laptop, and avoid running Whisper alongside several other heavy development containers. For regular voice use, move transcription to a separate cloud worker or use the device/browser dictation fallback.

Start with `docker compose --profile transcription up -d --build` after setting `WHISPER_WORKER_TOKEN` in the API `.env`. The API passes only the worker token and model settings to this container; it does not pass Supabase or model-provider secrets.
