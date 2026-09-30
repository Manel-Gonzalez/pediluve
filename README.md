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

A session itself is created up front over the REST API, not implicitly by the WebSocket — the
home page's "New session" modal names it, then opens its live view, which joins that same session
over the WebSocket rather than creating a new one:

```
┌──────────┐  POST /api/sessions  ┌──────────┐
│  Browser │ ────────────────────►│ FastAPI  │──► Supabase (sessions row created)
│  (home)  │ ◄────────────────────│  (REST)  │
└──────────┘   {id, title, ...}   └──────────┘
     │
     │ navigate to /sessions/:id/live
     ▼
```

Once on the live view, that JWT rides along on every WebSocket message, the connection joins the
session that was just created (or an existing one, on a pause/resume), and the audio itself
streams continuously rather than in fixed-size chunks:

```
┌─────────────────────┐  authenticate, join_session   ┌────────────┐                    ┌───────────────┐
│   Browser (React)   │───────► raw PCM + JWT ───────►│  FastAPI   │─── realtime WS ───►│  ElevenLabs   │
│ mic -> AudioWorklet │◄── session_joined, partial/ ───│  (Python)  │◄ partial/committed │  Scribe (RT)  │
└─────────────────────┘        committed transcripts   └────────────┘                    └───────────────┘
```

FastAPI then calls DeepL (REST) to translate each committed transcript, and Supabase (Postgres,
via that same user's JWT so Row Level Security applies) to persist it - both described below.

**Flow, once a session is joined:**
1. Browser captures mic audio with the Web Audio API + an `AudioWorklet`, streaming raw PCM continuously over WebSocket (no `MediaRecorder`/WebM — ElevenLabs' realtime endpoint needs uncompressed audio, so there's no container to convert)
2. Backend proxies that stream straight through to ElevenLabs' realtime STT WebSocket and relays `partial_transcript`/`committed_transcript` events back as they arrive
3. On each committed transcript, backend calls DeepL for translation
4. Backend pushes `{original_text, translated_text}` back over the same WebSocket
5. Backend persists the message to Supabase, scoped to the signed-in user and the joined session — Row Level Security, not application code, is what stops one user from ever reading another's rows
6. Browser renders both texts side by side, live

Recording can be paused and resumed any number of times within the same session (pausing doesn't
end it — only leaving the live view does); the session's full transcript stays available afterward
at its own read-only URL, from the sessions list on the home page.

## Stack

| Layer | Tech | Why |
|---|---|---|
| Frontend | React + Vite + TypeScript | Fast dev loop, familiar |
| Backend | Python + FastAPI | Async WebSocket support, same language as the original |
| STT | ElevenLabs Scribe (realtime) | Same provider as the original system, true streaming |
| Translation | DeepL API (Free tier) | 500k chars/month free, low latency |
| Auth | Supabase Auth (email + password) | No custom auth endpoints to build or secure |
| Routing | React Router | `/login` + per-session URLs, survives a reload |
| Styling | Tailwind CSS | Design tokens (colors, type scale) instead of hand-rolled CSS per component |
| TTS | ElevenLabs | Optional, on-demand playback |
| Persistence | Supabase (PostgreSQL) | Free tier, hosted, Row Level Security scopes data per user |

Everything runs on `localhost`. No deployment in v1.

## Roadmap

- [x] **Phase 0 — Setup**: repo structure, WebSocket echo, Supabase tables
- [x] **Phase 1 — Audio streaming**: mic → realtime STT → text on screen, persisted to Supabase
- [x] **Phase 2 — Translation**: target language selector, DeepL, side-by-side view
- [x] **Phase 3 — Accounts**: Supabase Auth (email + password), React Router (`/login` + a guarded app), sessions scoped to the signed-in user via Row Level Security
- [x] **Phase 4 — Session-first flow**: name and create a session explicitly (home page → "New session"), its live view joins that session over the WebSocket and can be paused/resumed without ending it, a past session's full transcript is a read-only page, re-translate it to another language on demand, rename/delete from the home list
- [x] **Phase 4.5 — Visual design**: Tailwind CSS with a small design-token system (colors, type scale), every page/component migrated off hand-written CSS, a redesigned paired-card transcript view
- [ ] **Phase 5 — TTS** *(current)*: play a translated message back, generated once and cached in Supabase Storage
- [ ] **Phase 6 — Spike**: speaker labels, only if a real multi-mic use case shows up; further voice-activity-detection tuning

## Running locally

### Supabase setup (one-time)

1. Create a project at [supabase.com](https://supabase.com) (or use an existing one).
2. **Authentication → Providers → Email**: make sure it's enabled.
3. **Authentication → Providers → Email → "Confirm email"**: turn this **off** for local dev (recommended) — with it on, registering returns no session until the user clicks a confirmation link, which needs an email template and a working "from" address neither of which this project sets up. Leave it on only if you specifically want to test that flow.
4. **SQL Editor → New query**: run, in order, `supabase/migrations/001_initial.sql`, `003_auth_and_rls.sql`, then `004_nullable_target_language.sql` (`002_disable_rls.sql` is superseded by 003 and only kept as history — skip it). This creates the schema, adds `sessions.user_id`, turns on Row Level Security with owner-only policies, and (004) makes `sessions.target_language` nullable and adds a `unique(session_id, sequence)` constraint on `messages`.
5. **Project Settings → API**: copy the Project URL and the `anon` `public` key (never the `service_role` key — it bypasses Row Level Security entirely) for the `.env` files below.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # fill in your keys (ElevenLabs, DeepL, Supabase URL + anon key)
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` (not just `localhost`) so a phone on the same Wi-Fi can reach the backend too -
needed for the QR live viewer (KAN-50): the mic-capturing owner needs a secure context, so keep
recording on `http://localhost:5173`, but the anonymous viewer opens the share link at your
machine's LAN IP instead. Add that LAN origin (e.g. `http://192.168.1.42:5173`) to `CORS_ORIGINS`
in `backend/.env` alongside `http://localhost:5173`.

### Frontend

```bash
cd frontend
npm install
cp ../.env.example .env   # only the VITE_ vars in it are read here
npm run dev   # http://localhost:5173
```

Open `http://localhost:5173`, register an account (redirects to `/login` automatically until you
do), click **New session** on the home page and give it a name, then start recording on its live
view. Pause and resume as needed; **End session** returns you to the home page, where the session
now appears in the list — click it to revisit its full transcript, or use the row's Rename/Delete
actions.

## Decisions log

See [`docs/decisions.md`](docs/decisions.md) for why each tech was chosen over alternatives.

## Author

Manel Gonzalez Rico — [LinkedIn](https://linkedin.com/in/manel-gonzalez-rico) · [GitHub](https://github.com/Manel-Gonzalez)
