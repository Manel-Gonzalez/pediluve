# Decisions log

Why each choice was made. Update this when something changes.

## STT: ElevenLabs Scribe over Whisper

**Chosen:** ElevenLabs Scribe (REST API)
**Alternatives:** OpenAI Whisper API, Whisper running locally

**Why:** Same provider I used in the original system, so the integration patterns are familiar. Scribe handles multi-language detection well, including Catalan/Spanish mixing. Cost is comparable to Whisper API (~$0.40/hour of audio). Local Whisper would be free but needs GPU for acceptable latency.

**Revisit if:** costs grow beyond ~€10/month, or if I want to experiment with local models.

## Translation: DeepL over Claude/GPT

**Chosen:** DeepL API Free tier
**Alternatives:** Claude API, GPT API, Google Translate

**Why:** Free for 500k chars/month (plenty for a personal project). Lower latency than an LLM call (~300ms vs ~1s), which matters for real-time. Translation quality for ES/CA/EN/DE/FR is excellent.

**Trade-off:** DeepL translates each chunk in isolation — no conversational context. Pronouns and references across chunks may drift.

**Revisit in Phase 5:** add an optional "context mode" using Claude with the last N messages as context. Compare quality vs latency.

## Real-time: 2s chunks over WebSocket, not streaming STT

**Chosen:** Browser sends 2-second audio chunks; backend processes each one and pushes text back.
**Alternative:** ElevenLabs WebSocket streaming STT (word-by-word).

**Why:** Simpler to build and debug. The 2-3s delay is acceptable for a conversation aid (it's what the original system did too). Streaming STT is billed by connection time and is harder to get right.

**Revisit in Phase 5.**

## Persistence: Supabase over local SQLite

**Chosen:** Supabase (hosted PostgreSQL)
**Alternative:** SQLite file

**Why:** I already know Supabase from a previous project. Zero local DB setup. Free tier is plenty. Easy to inspect data from the dashboard. If I ever deploy this, the DB is already remote.

## Backend: FastAPI over Flask/Express

**Chosen:** Python + FastAPI
**Alternatives:** Flask, Node.js + Express

**Why:** Native async support for WebSockets. Pydantic models for free. Same language as the original system. Several job postings I'm looking at ask for FastAPI specifically.

## Frontend: Vite + React over Next.js

**Chosen:** Vite + React + TypeScript
**Alternative:** Next.js

**Why:** No need for SSR or routing in v1 — it's a single-page tool. Vite's dev server is faster. Less boilerplate. Next.js would be overkill here.
