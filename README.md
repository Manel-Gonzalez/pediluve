# Pédiluve 🎙️

Real-time speech transcription and translation, running locally.

Speak into your mic → see your words transcribed → see them translated → optionally hear the translation spoken back.

## Why

At my previous job I co-built a real-time simultaneous translation system for municipal front-desk services (Python on AWS ECS, React, WebSockets, ElevenLabs). I also started a solo project called Raptor on the same idea that never shipped.

Pédiluve is my local rebuild of that architecture: full control over the pipeline, cheap to run, and a base to experiment with the parts that were left pending (speaker diarization, streaming STT, contextual translation).

## Architecture

Sign-up/sign-in/sign-out talk to Supabase Auth directly from the browser (`supabase-js`) — the
backend never sees a password, only the JWT that comes back from it:

```
┌─────────────┐   email + password    ┌──────────────┐
│   Browser    │ ──────────────────►  │ Supabase Auth │
│ (supabase-js)│ ◄──────────────────  │               │
└─────────────┘    session + JWT      └──────────────┘
```

Once signed in, that JWT rides along on every WebSocket message, and the audio itself streams
continuously rather than in fixed-size chunks:

```
┌─────────────────────┐                    ┌────────────┐                    ┌───────────────┐
│   Browser (React)   │── raw PCM + JWT ──►│  FastAPI   │─── realtime WS ───►│  ElevenLabs   │
│ mic -> AudioWorklet │◄ partial/committed │  (Python)  │◄ partial/committed │  Scribe (RT)  │
└─────────────────────┘                    └────────────┘                    └───────────────┘
```

FastAPI then calls DeepL (REST) to translate each committed transcript, and Supabase (Postgres,
via that same user's JWT so Row Level Security applies) to persist it - both described below.

**Flow, once signed in:**
1. Browser captures mic audio with the Web Audio API + an `AudioWorklet`, streaming raw PCM continuously over WebSocket (no `MediaRecorder`/WebM — ElevenLabs' realtime endpoint needs uncompressed audio, so there's no container to convert)
2. Backend proxies that stream straight through to ElevenLabs' realtime STT WebSocket and relays `partial_transcript`/`committed_transcript` events back as they arrive
3. On each committed transcript, backend calls DeepL for translation
4. Backend pushes `{original_text, translated_text}` back over the same WebSocket
5. Backend persists the message to Supabase, scoped to the signed-in user — Row Level Security, not application code, is what stops one user from ever reading another's rows
6. Browser renders both texts side by side, live

## Stack

| Layer | Tech | Why |
|---|---|---|
| Frontend | React + Vite + TypeScript | Fast dev loop, familiar |
| Backend | Python + FastAPI | Async WebSocket support, same language as the original |
| STT | ElevenLabs Scribe (realtime) | Same provider as the original system, true streaming |
| Translation | DeepL API (Free tier) | 500k chars/month free, low latency |
| Auth | Supabase Auth (email + password) | No custom auth endpoints to build or secure |
| Routing | React Router | `/login` + per-session URLs, survives a reload |
| TTS | ElevenLabs | Optional, on-demand playback |
| Persistence | Supabase (PostgreSQL) | Free tier, hosted, Row Level Security scopes data per user |

Everything runs on `localhost`. No deployment in v1.

## Roadmap

- [x] **Phase 0 — Setup**: repo structure, WebSocket echo, Supabase tables
- [x] **Phase 1 — Audio streaming**: mic → realtime STT → text on screen, persisted to Supabase
- [x] **Phase 2 — Translation**: target language selector, DeepL, side-by-side view
- [ ] **Phase 3 — Accounts** *(current)*: Supabase Auth (email + password), React Router (`/login` + a guarded app), sessions scoped to the signed-in user via Row Level Security
- [ ] **Phase 4 — History**: list past sessions, open one on its own URL, re-translate to another language on demand, rename/delete
- [ ] **Phase 5 — TTS**: play a translated message back, generated once and cached in Supabase Storage
- [ ] **Phase 6 — Spike**: speaker labels, only if a real multi-mic use case shows up; further voice-activity-detection tuning

## Running locally

### Supabase setup (one-time)

1. Create a project at [supabase.com](https://supabase.com) (or use an existing one).
2. **Authentication → Providers → Email**: make sure it's enabled.
3. **Authentication → Providers → Email → "Confirm email"**: turn this **off** for local dev (recommended) — with it on, registering returns no session until the user clicks a confirmation link, which needs an email template and a working "from" address neither of which this project sets up. Leave it on only if you specifically want to test that flow.
4. **SQL Editor → New query**: run `supabase/migrations/001_initial.sql`, then `supabase/migrations/003_auth_and_rls.sql` (`002_disable_rls.sql` is superseded by 003 and only kept as history — skip it). This creates the schema, adds `sessions.user_id`, and turns on Row Level Security with owner-only policies.
5. **Project Settings → API**: copy the Project URL and the `anon` `public` key (never the `service_role` key — it bypasses Row Level Security entirely) for the `.env` files below.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # fill in your keys (ElevenLabs, DeepL, Supabase URL + anon key)
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp ../.env.example .env   # only the VITE_ vars in it are read here
npm run dev   # http://localhost:5173
```

Open `http://localhost:5173`, register an account (redirects to `/login` automatically until you
do), then start recording.

## Decisions log

See [`docs/decisions.md`](docs/decisions.md) for why each tech was chosen over alternatives.

## Author

Manel Gonzalez Rico — [LinkedIn](https://linkedin.com/in/manel-gonzalez-rico) · [GitHub](https://github.com/Manel-Gonzalez)
