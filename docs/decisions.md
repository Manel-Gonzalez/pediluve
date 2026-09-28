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

## Future: production deploy on AWS (not started, notes for later)

**If this ever needs to run in production:**

- **Backend: ECS Fargate, not Lambda.** The WebSocket connection stays open while audio chunks stream in. Lambda + API Gateway WebSocket would mean every message is a separate invocation, with connection state pushed into DynamoDB between them — a lot of rearchitecting for a project this size. Fargate keeps the current always-on FastAPI process model.
- **DB: RDS Postgres instead of Supabase.** Same schema, same SQL migrations in `supabase/migrations/`, just a different connection string. No need for DynamoDB or Aurora.
- **Frontend: S3 + CloudFront**, built as a static Vite bundle, fully decoupled from the backend.
- **Repo stays a monorepo.** Two GitHub Actions workflows with path filters (`frontend/**`, `backend/**`) build and deploy each side independently — no need to split into separate repos for this.

**Revisit:** only if/when an actual deploy is planned. Phase 0-5 stay local-only per `CLAUDE.md`.
