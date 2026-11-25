# Charvi API / AI connection blocker

Checked: 25 November 2026

## Finding

The separate `charvi-api` Vercel project initially had no custom environment variables. I have now added `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` from the already-configured frontend project to the API project for Production and Preview. The private database credential and model-provider credentials are still missing and must be supplied by the account owner.

The API source requires these server-side variables:

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`

Without the first two, API bearer-token validation returns `Authentication is not configured.`. Without the service-role key, database operations return `Charvi's private database connection is not configured.`.

The AI coordinator code exists, but it is not the same as a connected model. `AgentSettings.coordinator_provider` defaults to `ollama`. The default Ollama adapter requires `OLLAMA_BASE_URL` and `OLLAMA_MODEL`. No model-provider credentials were visible, so a model provider has not been configured there.

## Recommended connection: OpenAI API

In Vercel, open the separate `charvi-api` project, then Settings → Environment Variables. `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` are already set for Production and Preview. Add the remaining variables:

| Variable | Value |
|---|---|
| `SUPABASE_URL` | Same Supabase project URL as the frontend's `NEXT_PUBLIC_SUPABASE_URL` |
| `SUPABASE_PUBLISHABLE_KEY` | Same public/publishable key as frontend's `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service-role secret; server-side only |
| `COORDINATOR_PROVIDER` | `openai` |
| `OPENAI_API_KEY` | Your OpenAI Platform API key |
| `OPENAI_MODEL` | A model ID enabled for your OpenAI API project |

Then redeploy `charvi-api`.

Important: ChatGPT subscriptions do not include OpenAI API credits. API usage is billed separately by OpenAI. Never put `OPENAI_API_KEY` or `SUPABASE_SERVICE_ROLE_KEY` in the frontend project or any `NEXT_PUBLIC_*` variable. Do not paste either secret into chat, GitHub, or a Markdown support file.

## Alternative: OpenAI-compatible provider

If you choose another provider that exposes an OpenAI-compatible chat-completions endpoint, set:

- `COORDINATOR_PROVIDER=compatible`
- `COMPATIBLE_BASE_URL`
- `COMPATIBLE_API_KEY`
- `COMPATIBLE_MODEL`

Only use a provider's documented endpoint and model ID.

## After configuring

1. Redeploy the API.
2. Sign in to Charvi and open the model status section.
3. Confirm the coordinator reports `configured: true`.
4. Submit a harmless test prompt such as: "Summarise the purpose of Charvi in three sentences."
5. Confirm the run returns a completed coordinator result.
6. Check API runtime logs if it fails.

## Navigation work completed separately

The main navigation has been reduced to four meaningful expandable areas:

1. Home — Command Centre, Charvi AI, Analytics, Reports, Activity.
2. Work — Agents & Workforce, Departments, Tasks & Projects, Automations.
3. Knowledge — Knowledge Hub, Memory Vault.
4. Control — Approvals, Integrations, Devices, Settings/Profile, Screen coverage.

The four parent options remain visible; their related screens are nested inside each parent rather than shown as a long flat list.

## What is still blocked

I can implement and test the provider adapter code, but I cannot manufacture your private OpenAI API key or Supabase service-role secret. Those need to be entered directly into the Vercel `charvi-api` project's encrypted environment settings by the account owner.
