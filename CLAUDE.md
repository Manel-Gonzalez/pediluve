# Pédiluve — instructions for Claude Code

Read this before doing anything in this repo.

## What this project is

Real-time speech transcription + translation app, running locally. Browser captures raw PCM mic audio and streams it continuously over WebSocket to a FastAPI backend, which proxies it to ElevenLabs' realtime STT WebSocket, calls DeepL (translation), and persists to Supabase. See `README.md` for the full architecture diagram.

This is a portfolio project. Code quality and clear structure matter more than speed. It will be shown to recruiters.

## Stack (do not change without asking)

- **Frontend:** React 18 + Vite + TypeScript. Plain CSS or Tailwind — no component libraries unless asked.
- **Backend:** Python 3.11+ + FastAPI + `websockets`. Use `uvicorn` for dev.
- **STT:** ElevenLabs Scribe **realtime** (`scribe_v2_realtime`, `wss://api.elevenlabs.io/v1/speech-to-text/realtime`). Backend proxies: browser streams raw PCM to our own `/ws`, backend forwards it to ElevenLabs' WebSocket and relays `partial_transcript`/`committed_transcript` events back. No diarization on this endpoint — REST batch (`scribe_v2`) is the fallback if we ever need speaker separation.
- **Translation:** DeepL API Free tier.
- **TTS:** ElevenLabs (Phase 5 only), single fixed voice (`ELEVENLABS_VOICE_ID`) — no per-language voice mapping in v1.
- **DB:** Supabase (PostgreSQL). Use the `supabase-py` client. Schema in `supabase/migrations/`.
- **Auth:** Supabase Auth (Phase 3 only), email + password. No other provider (no OAuth, no magic link) in v1.
- **Routing:** React Router, introduced in Phase 3 (`/login`, `RequireAuth`-guarded routes) — Phase 4 adds routable per-session URLs on top of the same router rather than introducing one from scratch. No routing before Phase 3.
- **Audio capture:** Web Audio API + `AudioWorklet`, raw PCM (`pcm_16000` or whatever the browser's `AudioContext` actually negotiates). No `MediaRecorder`/WebM, no `pydub`/`ffmpeg` — ElevenLabs realtime needs uncompressed audio, so there's no container to convert.

## Repo structure

```
pediluve/
├── README.md
├── CLAUDE.md              ← this file
├── .env.example           ← all env vars documented here
├── .gitignore
├── docs/
│   └── decisions.md       ← why X over Y, keep it updated
├── frontend/
│   ├── src/
│   │   ├── components/    ← AuthForm, Nav, RequireAuth (route guard)
│   │   ├── hooks/         ← useWebSocket, useMicrophone, useAuth (AuthProvider)
│   │   ├── pages/         ← LoginPage, RecordPage (routed from App.tsx)
│   │   ├── lib/           ← api client, types, auth/languageControls helpers
│   │   ├── audio/         ← pcm-worklet.js (AudioWorkletProcessor)
│   │   ├── App.tsx        ← route table only (RequireAuth + pages/)
│   │   └── main.tsx       ← AuthProvider + BrowserRouter wiring
│   ├── package.json
│   └── vite.config.ts
├── backend/
│   ├── main.py            ← FastAPI app, WebSocket endpoint
│   ├── routers/           ← ws.py, me.py (GET /me)
│   ├── services/
│   │   ├── elevenlabs.py
│   │   ├── deepl.py
│   │   ├── supabase.py
│   │   └── auth.py        ← verify_access_token (Supabase Auth)
│   ├── models/            ← Pydantic schemas
│   ├── requirements.txt
│   └── .env               ← gitignored
└── supabase/
    └── migrations/
        ├── 001_initial.sql
        ├── 002_disable_rls.sql   ← superseded by 003, kept as history
        └── 003_auth_and_rls.sql  ← sessions.user_id, RLS + owner policies
```

## Conventions

- **Language:** code, comments, commit messages, and docs in **English**. UI strings can be in English for now.
- **Commits:** conventional commits. `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`. One logical change per commit.
- **Branches:** work on `main` for Phase 0. From Phase 1 on, one branch per Jira card: `feature/<KAN-N>` for a feature (a phase's parent Story, e.g. `feature/KAN-4`), `fix/<KAN-N>` for a bug fix, `chore/<KAN-N>` for anything else — prefix matches the card's nature, not its issue type. Subtasks are commits on the parent card's branch, not their own branches. Merge to `main` when the card's work is done and (for a phase) works end-to-end.
- **Types:** TypeScript strict mode on. Pydantic models for every request/response shape.
- **Secrets:** never hardcode API keys. Read from `.env`. Never commit `.env`.
- **Errors:** WebSocket errors go back to the client as `{type: "error", message: "..."}`. Don't let the socket die silently.
- **Testing:** TDD for backend services and pure frontend logic — write the test first, watch it fail, then implement (`pytest` for backend, mock `RealtimeTranscriptionSession` rather than hitting the real ElevenLabs API; `vitest` for frontend pure functions). Don't force it onto browser-API-heavy code (`AudioWorklet`, `MediaStream`) — mocking those gives fragile, low-confidence tests; verify that by hand in a real browser instead. For any non-trivial new feature, write a short spec (what it does, the message contract, acceptance criteria) before the test.

## Phase gates

Do not start a phase until the previous one works end-to-end and is merged to `main`.

**Phase 0:** repo skeleton, WebSocket echo (frontend sends text, backend echoes it back), Supabase tables created via migration, `.env.example` complete.

**Phase 1:** mic capture → raw PCM streamed continuously over WebSocket → backend proxies to ElevenLabs realtime STT → partial/committed transcript text back over WebSocket → rendered in UI. Save each committed message to Supabase.

**Phase 2:** language selector in UI → backend calls DeepL after STT → both texts sent back → two-column view. Save translation alongside original.

**Phase 3 (current):** user accounts. Supabase Auth, email + password — login/register/logout,
React Router introduced for `/login` + a `RequireAuth`-guarded app (see `docs/decisions.md` for why
routing moved here instead of Phase 4). Sessions and messages get scoped to the authenticated user
(`sessions.user_id`, RLS policies so a user only ever sees their own data). Comes before Phase 4
because "list of my past sessions" is meaningless without knowing who "I" am first.

**Phase 4:** sessions list page (the authenticated user's own sessions) → open a past session,
each on its own routable URL (added to the router introduced in Phase 3) so a reload doesn't bounce
back to home → re-translate to a different language **computed on demand, not persisted** (the original live-session
translation stays in `messages.translated_text`/`target_language` untouched; viewing history in
another language just calls DeepL again for that view) → rename or delete a session (mini CRUD;
`sessions.title` already exists for the rename, `messages` already cascade-deletes with the
session).

**Phase 5:** "play" button per translated message → ElevenLabs TTS → audio generated once and
cached in Supabase Storage (a repeat play serves the stored file, not a fresh paid TTS call) →
playback in browser. One fixed voice for v1, not one per language.

**Phase 6 (parked, exploratory only):** speaker labels if multiple audio inputs. No multi-channel
capture exists yet and there's no confirmed use case for it — start with a spike (is there a real
multi-mic scenario? is `use_multi_channel` viable, or REST batch the only path?) before committing
to implementation subtasks. Realtime STT has no diarization on its own. Also: further VAD tuning.

## What NOT to do

- Don't add multi-tenant/org complexity — Phase 3 adds per-user accounts (Supabase Auth), not
  roles, teams, or admin features. Each user only ever sees their own sessions.
- Don't add Docker in v1. `uvicorn` + `npm run dev` is enough.
- Don't add a state management library (Redux, Zustand). React state + context is enough.
- Don't add tests in Phase 0. Add them from Phase 1 on for the backend services (done — see `backend/tests/`).
- Don't deploy anywhere. Local only.
- Don't over-engineer. If a file is under 50 lines and does one thing, that's good.

## When you're unsure

Ask before:
- Adding a new dependency
- Changing the folder structure
- Changing the WebSocket message format

Don't ask, just do:
- Fixing a bug you found
- Adding a missing type
- Improving an error message

## Current status

Phase 2 — done and merged to `main`.

Phase 3 (current) — user accounts, in progress. Implemented, tested, and code-reviewed: KAN-14
(`GET /me` + `verify_access_token`), KAN-16 (per-user Supabase client, RLS-safe writes), KAN-18
(`/ws` authenticate handshake + auth gate), KAN-15 (frontend `supabase-js` client, `AuthProvider`,
`AuthForm`), KAN-17 (React Router shell — `/login`, `RequireAuth`, `RecordPage`, `Nav`) and KAN-19
(`useWebSocket` authenticate/refresh/close-on-signout). KAN-13 (migration `003_auth_and_rls.sql`)
is written but **not yet applied** to the real Supabase project — apply it via `README.md`'s
Supabase setup steps once ready. Nothing in Phase 3 has been verified end-to-end yet in a real
browser with a real Supabase project and RLS on (pending: apply the migration, then walk through
login/register, two-account RLS isolation, sign-out mid-recording, and a recording surviving a JWT
refresh). Backend tests (`pytest`, 85 passing) and frontend tests (`vitest`, 29 passing). Next:
apply migration 003, verify Phase 3 end-to-end, merge to `main`.
