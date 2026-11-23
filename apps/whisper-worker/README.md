# Charvi private Whisper worker

This optional worker provides self-hosted speech-to-text for dashboard voice recordings.

- Uses faster-whisper with the multilingual `tiny` model by default.
- Defaults to CPU + INT8 so it does not require an NVIDIA GPU.
- Supports language hints for English (`en`), Hindi (`hi`) and Kannada (`kn`), plus Whisper's automatic language detection when omitted.
- Accepts audio up to 20 MB in WebM, Ogg, WAV, MP3, MP4/AAC or FLAC.
- Keeps uploaded audio in a temporary file only while the request is processed and deletes it afterwards.
- Requires a shared worker token; never exposes the worker port to the host.
- Model files persist in the named `whisper-model-cache` Docker volume.

The tiny model is a conservative first configuration because the laptop hardware has not yet been confirmed. Increase `WHISPER_MODEL_SIZE` only after testing memory and latency on the actual host.

Start with `docker compose --profile voice up -d --build` after setting `WHISPER_WORKER_TOKEN` in the API `.env`. The API passes only the worker token and model settings to this container; it does not pass Supabase or model-provider secrets.
