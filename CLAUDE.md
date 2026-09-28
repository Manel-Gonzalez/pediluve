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
- **TTS:** ElevenLabs (Phase 4 only).
- **DB:** Supabase (PostgreSQL). Use the `supabase-py` client. Schema in `supabase/migrations/`.
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
│   │   ├── components/
│   │   ├── hooks/         ← useWebSocket, useMicrophone
│   │   ├── lib/           ← api client, types
│   │   ├── audio/         ← pcm-worklet.js (AudioWorkletProcessor)
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
├── backend/
│   ├── main.py            ← FastAPI app, WebSocket endpoint
│   ├── routers/
│   ├── services/
│   │   ├── elevenlabs.py
│   │   ├── deepl.py
│   │   └── supabase.py
│   ├── models/            ← Pydantic schemas
│   ├── requirements.txt
│   └── .env               ← gitignored
└── supabase/
    └── migrations/
        └── 001_initial.sql
```

## Conventions

- **Language:** code, comments, commit messages, and docs in **English**. UI strings can be in English for now.
- **Commits:** conventional commits. `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`. One logical change per commit.
- **Branches:** work on `main` for Phase 0. From Phase 1 on, one branch per phase (`phase-1-audio`, `phase-2-translation`, etc.), merge to `main` when the phase works end-to-end.
- **Types:** TypeScript strict mode on. Pydantic models for every request/response shape.
- **Secrets:** never hardcode API keys. Read from `.env`. Never commit `.env`.
- **Errors:** WebSocket errors go back to the client as `{type: "error", message: "..."}`. Don't let the socket die silently.
- **Testing:** TDD for backend services and pure frontend logic — write the test first, watch it fail, then implement (`pytest` for backend, mock `RealtimeTranscriptionSession` rather than hitting the real ElevenLabs API; `vitest` for frontend pure functions). Don't force it onto browser-API-heavy code (`AudioWorklet`, `MediaStream`) — mocking those gives fragile, low-confidence tests; verify that by hand in a real browser instead. For any non-trivial new feature, write a short spec (what it does, the message contract, acceptance criteria) before the test.

## Phase gates

Do not start a phase until the previous one works end-to-end and is merged to `main`.

**Phase 0 (current):** repo skeleton, WebSocket echo (frontend sends text, backend echoes it back), Supabase tables created via migration, `.env.example` complete.

**Phase 1:** mic capture → raw PCM streamed continuously over WebSocket → backend proxies to ElevenLabs realtime STT → partial/committed transcript text back over WebSocket → rendered in UI. Save each committed message to Supabase.

**Phase 2:** language selector in UI → backend calls DeepL after STT → both texts sent back → two-column view. Save translation alongside original.

**Phase 3:** sessions list page → open a past session → re-translate all messages to a different language.

**Phase 4:** "play" button per translated message → ElevenLabs TTS → audio playback in browser.

**Phase 5:** speaker labels if multiple audio inputs (realtime STT has no diarization — would need `use_multi_channel` or falling back to REST batch), further VAD tuning.

## What NOT to do

- Don't add authentication. Single-user local app.
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

Phase 1 — done, merged to `main`. Mic capture (`AudioWorklet`, raw PCM) → backend proxy → ElevenLabs realtime STT → committed transcripts persisted to Supabase (`sessions`/`messages`), verified end-to-end with real speech and real data in the database. `sessions.target_language` gets a placeholder (`"en"`) until Phase 2 adds the real selector. Backend tests (`pytest`, 22 passing) and frontend tests (`vitest`, 4 passing). Next: Phase 2 (language selector, DeepL translation, two-column view) on a new branch, `phase-2-translation`.
