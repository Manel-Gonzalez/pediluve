# Pédiluve 🎙️

Real-time speech transcription and translation, running locally.

Speak into your mic → see your words transcribed → see them translated → optionally hear the translation spoken back.

## Why

At my previous job I co-built a real-time simultaneous translation system for municipal front-desk services (Python on AWS ECS, React, WebSockets, ElevenLabs). I also started a solo project called Raptor on the same idea that never shipped.

Pédiluve is my local rebuild of that architecture: full control over the pipeline, cheap to run, and a base to experiment with the parts that were left pending (speaker diarization, streaming STT, contextual translation).

## Architecture

```
┌─────────────┐   WebSocket    ┌──────────────┐   REST    ┌─────────────┐
│   Browser   │ ─────────────► │   FastAPI    │ ────────► │ ElevenLabs  │
│  (React)    │  audio chunks  │  (Python)    │   STT     │   Scribe    │
│             │ ◄───────────── │              │ ◄──────── │             │
│  mic → 2s   │  {orig, trans} │              │   text    └─────────────┘
│  chunks     │                │              │
└─────────────┘                │              │   REST    ┌─────────────┐
                               │              │ ────────► │   DeepL     │
                               │              │ ◄──────── │   (free)    │
                               │              │           └─────────────┘
                               │              │
                               │              │           ┌─────────────┐
                               │              │ ────────► │  Supabase   │
                               └──────────────┘  persist  │ (Postgres)  │
                                                          └─────────────┘
```

**Flow per chunk (every ~2 seconds):**
1. Browser captures mic audio with `MediaRecorder`, sends a 2s chunk over WebSocket
2. Backend converts WebM → WAV, sends to ElevenLabs Scribe (STT)
3. Backend sends transcribed text to DeepL for translation
4. Backend pushes `{original, translated, timestamp}` back over WebSocket
5. Backend persists the message to Supabase
6. Browser renders both texts side by side

## Stack

| Layer | Tech | Why |
|---|---|---|
| Frontend | React + Vite + TypeScript | Fast dev loop, familiar |
| Backend | Python + FastAPI | Async WebSocket support, same language as the original |
| STT | ElevenLabs Scribe | Same provider as the original system |
| Translation | DeepL API (Free tier) | 500k chars/month free, low latency |
| TTS | ElevenLabs | Optional, on-demand playback |
| Persistence | Supabase (PostgreSQL) | Free tier, hosted, no local DB to manage |

Everything runs on `localhost`. No deployment in v1.

## Roadmap

- [x] **Phase 0 — Setup**: repo structure, WebSocket echo, Supabase tables
- [ ] **Phase 1 — Audio streaming**: mic → chunks → STT → text on screen
- [ ] **Phase 2 — Translation**: target language selector, DeepL, side-by-side view
- [ ] **Phase 3 — History**: list past sessions, re-translate a session to another language
- [ ] **Phase 4 — TTS**: play translated text on demand
- [ ] **Phase 5 — Polish**: voice activity detection, speaker labels, streaming STT

## Running locally

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # fill in your keys
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev   # http://localhost:5173
```

## Decisions log

See [`docs/decisions.md`](docs/decisions.md) for why each tech was chosen over alternatives.

## Author

Manel Gonzalez Rico — [LinkedIn](https://linkedin.com/in/manel-gonzalez-rico) · [GitHub](https://github.com/Manel-Gonzalez)
