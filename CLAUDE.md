# Pédiluve — instructions for Claude Code

Read this before doing anything in this repo.

## What this project is

Real-time speech transcription + translation app, running locally. Browser captures mic audio, sends 2s chunks over WebSocket to a FastAPI backend, which calls ElevenLabs (STT), DeepL (translation), and persists to Supabase. See `README.md` for the full architecture diagram.

This is a portfolio project. Code quality and clear structure matter more than speed. It will be shown to recruiters.

## Stack (do not change without asking)

- **Frontend:** React 18 + Vite + TypeScript. Plain CSS or Tailwind — no component libraries unless asked.
- **Backend:** Python 3.11+ + FastAPI + `websockets`. Use `uvicorn` for dev.
- **STT:** ElevenLabs Scribe via REST API (not their WebSocket streaming yet — that's Phase 5).
- **Translation:** DeepL API Free tier.
- **TTS:** ElevenLabs (Phase 4 only).
- **DB:** Supabase (PostgreSQL). Use the `supabase-py` client. Schema in `supabase/migrations/`.
- **Audio conversion:** `pydub` + `ffmpeg` for WebM → WAV.

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

## Phase gates

Do not start a phase until the previous one works end-to-end and is merged to `main`.

**Phase 0 (current):** repo skeleton, WebSocket echo (frontend sends text, backend echoes it back), Supabase tables created via migration, `.env.example` complete.

**Phase 1:** mic capture → 2s WebM chunks → backend converts to WAV → ElevenLabs STT → text back over WebSocket → rendered in UI. Save each message to Supabase.

**Phase 2:** language selector in UI → backend calls DeepL after STT → both texts sent back → two-column view. Save translation alongside original.

**Phase 3:** sessions list page → open a past session → re-translate all messages to a different language.

**Phase 4:** "play" button per translated message → ElevenLabs TTS → audio playback in browser.

**Phase 5:** voice activity detection (skip silent chunks), speaker labels if multiple audio inputs, evaluate ElevenLabs streaming STT.

## What NOT to do

- Don't add authentication. Single-user local app.
- Don't add Docker in v1. `uvicorn` + `npm run dev` is enough.
- Don't add a state management library (Redux, Zustand). React state + context is enough.
- Don't add tests in Phase 0. Add them from Phase 1 on for the backend services.
- Don't deploy anywhere. Local only.
- Don't use ElevenLabs WebSocket streaming until Phase 5. REST is fine.
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

Phase 0 — done. Repo skeleton in place, WebSocket echo verified end-to-end (frontend ↔ backend), Supabase migration applied. Next: Phase 1 (audio streaming).
