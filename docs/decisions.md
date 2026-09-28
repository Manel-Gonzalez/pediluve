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

## Real-time: ElevenLabs realtime streaming STT, not REST batch chunks

**Chosen (reversed from the original plan):** browser streams raw PCM continuously; backend proxies it to ElevenLabs' realtime WebSocket (`scribe_v2_realtime`) and relays `partial_transcript`/`committed_transcript` events back.
**Original plan (Phase 0):** browser sends 2-second WebM chunks; backend converts each to WAV and calls the REST batch endpoint (`scribe_v2`) per chunk.

**Why the reversal:** the original REST-per-chunk plan was explicitly meant to be replaced by realtime streaming in Phase 5 anyway (see `CLAUDE.md`'s old phase gates) — building it twice made no sense. Doing realtime now also let us validate that the WebSocket actually carries the audio format ElevenLabs expects, and it matches the project's original motivation (a genuinely real-time simultaneous-translation tool) far better than word-delayed 2-3s chunks.

**Trade-off accepted:** realtime STT has **no diarization** (confirmed against the live API docs — the realtime config has no `diarize`/`num_speakers` params, only the REST batch endpoint does). If speaker separation becomes important, we'd need `use_multi_channel` (one audio channel per speaker) or fall back to REST batch for that specific need. Also more implementation complexity: raw PCM capture requires `AudioWorklet` instead of the simpler `MediaRecorder`, and the backend has to manage two concurrent WebSocket connections (browser ↔ backend ↔ ElevenLabs) instead of one-shot REST calls.

**Confirmed working (2026-09-28):** backend connects to ElevenLabs with the API key, gets `session_started` back with the right config, and the start/stop lifecycle doesn't leak connections or crash on disconnect. Not yet tested with real speech — only synthetic silence so far (correctly produces no transcript, since VAD found no speech).

## Phase 2: source_language not yet threaded into ElevenLabs, DeepL target-code mapping

**Context:** KAN-5 (DeepL integration + WebSocket contract) added a `source_language`
field to `start_transcription` and a `set_target_language` message. `source_language`
is parsed and stored on `ConnectionHandler` (for KAN-6 persistence and a future
Phase-3 re-translation use) but is **not** passed to
`RealtimeTranscriptionSession.connect()` yet.

**Why:** whether ElevenLabs' `scribe_v2_realtime` realtime endpoint accepts a
language-hint parameter at all is unconfirmed — `elevenlabs.io`/`api.elevenlabs.io`
are unreachable from the cloud sandbox this was built in (org network policy blocks
them), the same way `api-free.deepl.com` is. Guessing at an unverified query
parameter on an external realtime API risked silently breaking the STT connection.

**Revisit:** confirm from a machine with real network access, the same way the
no-diarization decision above was confirmed (live docs or the `session_started`
event payload). If a language-hint param exists, thread `source_language` through
in `services/elevenlabs.py::connect()`. If not, it stays a label used for
display/persistence only.

**Also unverified (same network restriction):** whether DeepL's `/v2/translate`
actually supports `CA` (Catalan) as a `target_lang` — `services/deepl.py`'s
`_TARGET_LANGUAGE_CODES` maps it optimistically. If DeepL rejects it, `translate()`
raises, which the WebSocket handler already treats as a per-message translation
failure (logged, `translated_text` stays null) rather than a crash — so this doesn't
block KAN-5, but Catalan-target translation may not actually work until confirmed
against DeepL's real supported-language list.

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
