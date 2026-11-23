# Charvi web owner console

The first web dashboard milestone provides:

- Supabase Auth email/password sign-in using cookie-backed SSR sessions.
- A workspace selector and first-workspace creation.
- Agent registry and coordinator model readiness.
- Task submission, thread continuity, run history and recovery.
- Explicit memory save/archive and memory opt-out.
- Pending approval review and decision.
- Dark/light themes and responsive layouts.

## Local setup

1. Copy `.env.example` to `.env.local`.
2. Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` using the project's public values.
3. Set `NEXT_PUBLIC_CHARVI_API_URL=http://localhost:8000`.
4. Configure the API's private `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SERVICE_ROLE_KEY` and `CORS_ALLOWED_ORIGINS=http://localhost:3000`.
5. Install and run:

```bash
npm install
npm run dev
```

Open http://localhost:3000.

Never place a Supabase service-role key or Postgres password in a `NEXT_PUBLIC_*` variable. The browser receives only the Supabase publishable key and the signed-in user's access token. All privileged database operations remain in the FastAPI control plane.

The dashboard requires a workspace. If none exists, create one from the first-run screen. Email confirmation settings are controlled by Supabase Auth.

## Current limits

The dashboard includes browser-based speech dictation (English India, Kannada and Hindi) and speech playback for the latest response. Browser speech recognition can use the browser/device speech provider and is not a private local transcription engine. A self-hosted Whisper worker is a later option for private/offline transcription.

This remains a text-first owner console with optional browser voice controls. The mobile app, notifications, live agent deployment and production hosting are later milestones.
