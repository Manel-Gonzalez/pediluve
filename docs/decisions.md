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

## Phase 2: sessions.target_language can hold a meaningless placeholder

**Context:** `sessions.target_language` is `not null` (schema constraint from
Phase 0/1). When a recording starts before the user has ever picked a target
language, KAN-6's `create_session()` still has to write *something* into that
column, so it falls back to `DEFAULT_TARGET_LANGUAGE` ("en") - the same Phase 1
placeholder. `ConnectionHandler.target_language` itself stays `None` in that case
(DeepL is correctly never called, every `messages.translated_text` for that
session stays null), but the `sessions` row ends up saying `target_language='en'`
as if the session had been translated to English.

**Why this is left as-is for now:** fixing it properly means making the column
nullable (a migration), which is a schema change beyond KAN-6's scope. The
placeholder doesn't cause a functional bug today - `ConnectionHandler.target_language`
is the real, independent signal for "should we call DeepL", never synced from the
DB default - but a future reader must not trust `sessions.target_language` alone
to mean "this session has translations".

**Revisit in Phase 3** ("open a past session, re-translate to a different
language"): a consumer must check whether any `messages.translated_text` is
non-null for that session, not just read `sessions.target_language`, to know
whether translation was ever actually used. Consider making the column nullable
at that point instead of carrying the placeholder further.

**Resolved in Phase 4 (KAN-22):** `supabase/migrations/004_nullable_target_language.sql`
drops the `not null` constraint, and `create_session()` no longer substitutes
`DEFAULT_TARGET_LANGUAGE` when none was chosen - it now writes `NULL`
directly, matching what `ConnectionHandler.target_language` (`None`) actually
meant the whole time. `DEFAULT_TARGET_LANGUAGE` itself was removed as dead
code (its only two call sites, `create_session()`'s own default and the
`_start_transcription` call passing it, both went away with this fix). No
backfill: existing rows with the old `"en"` placeholder keep it, harmlessly -
they still correctly have no translated messages either way, per the
"a future reader must not trust `sessions.target_language` alone" note above,
which still holds for those specific pre-existing rows.

**Also unverified (same network restriction):** whether DeepL's `/v2/translate`
actually supports `CA` (Catalan) as a `target_lang` — `services/deepl.py`'s
`_TARGET_LANGUAGE_CODES` maps it optimistically. If DeepL rejects it, `translate()`
raises, which the WebSocket handler already treats as a per-message translation
failure (logged, `translated_text` stays null) rather than a crash — so this doesn't
block KAN-5, but Catalan-target translation may not actually work until confirmed
against DeepL's real supported-language list.

## Phase reorder: user accounts (auth) inserted as Phase 3, before sessions list

**Context:** the original phase gates (Phase 0-5) never included authentication — the app was
single-user and local. While scoping the sessions-list feature, Manel decided he wants per-user
accounts ("each user can view their own past sessions"), reversing the earlier "don't add auth"
rule in `CLAUDE.md`.

**Why auth has to come before the sessions list, not after:** "list of my past sessions" only
means something once there is a concept of "my" — retrofitting `user_id` onto sessions after
building an account-agnostic list page would mean redoing the list/detail views' data-fetching
once auth lands. Doing it in the other order avoids that rework.

**Chosen for auth:** Supabase Auth, email + password. **Alternatives considered:** magic link
(no password to manage, but adds a dependency on email deliverability being fast enough to not
annoy a solo dev testing login repeatedly), Google OAuth (nicer UX for a portfolio demo, but needs
OAuth credentials set up in Google Cloud before any code can be written — extra setup cost for a
single-user-per-account app with no real "who are you" stakes).

**Chosen for routing:** React Router. Each session gets its own URL so a reload
or crash returns to that session, not to the home/list view — the alternative (React state only,
no router) was explicitly rejected because losing your place on a refresh is bad UX for something
you might have open for a while.

**Amendment (KAN-17): React Router moved from Phase 4 to Phase 3, not Phase 4 as first planned.**
The original reasoning above (per-session URLs) is still Phase 4's reason for *adding more routes*,
but it turned out Phase 3 needed *some* router before Phase 4 does: a real login page (`/login`,
bookmarkable, survives a reload, works with the browser back/forward buttons) and a "protected
route" guard for everything else are themselves a routing problem, not something worth faking with
conditional rendering inside a single unrouted `App`. Building that ad hoc in Phase 3 and then
introducing React Router "for real" in Phase 4 would mean redoing the login/guard logic as real
routes at that point anyway. Pulling the dependency forward once, in Phase 3, means Phase 4 only
ever adds routes to a router that already exists (`RequireAuth` as a layout route, `pages/` as the
established location) instead of introducing routing from scratch a phase later.

**Revisit:** RLS is currently disabled site-wide (`supabase/migrations/001_initial.sql` says so
explicitly, anticipating this exact moment) — Phase 3 must turn it on and add policies scoping
`sessions`/`messages` to `auth.uid()`, not just add a `user_id` column and trust the backend to
filter correctly on every query.

## Auth: supabase-js on the client, JWT verification + RLS via user token on the backend

**No custom auth endpoints.** The backend has no `/login`/`/register`/`/logout` routes of its own.
The frontend talks to Supabase Auth directly via `supabase-js` (`signUp`/`signInWithPassword`/
`signOut`, `hooks/useAuth.tsx`); the backend only ever receives an already-issued access token (the
WebSocket `authenticate` message, or the `Authorization` header on `GET /me`) and verifies it.
**Why:** Supabase Auth already handles password hashing, session issuance, refresh tokens, and
email-confirmation delivery — reimplementing any slice of that server-side would be pure duplicated
risk (a self-rolled auth endpoint is exactly the kind of thing that quietly gets the edge cases
wrong) for zero benefit over using the already-battle-tested client library directly.

**Anon key + per-request user JWT, never the service-role key.** `services/supabase.py::client_for()`
builds a fresh Postgrest client per call using the `anon` key, then explicitly authenticates it as
the calling user (`client.postgrest.auth(access_token)`) — every DB read/write runs as that user, so
Postgres' Row Level Security (`auth.uid()` policies, `supabase/migrations/003_auth_and_rls.sql`) is
the actual enforcement boundary, not application-level filtering. The service-role key (which
bypasses RLS entirely) is never used anywhere in this app. **Why:** defense in depth — even a bug in
the backend's own authorization logic can't leak another user's rows, because Postgres itself
refuses to return them.

**`get_user()` (a Supabase round-trip) over local JWT verification.** `services/auth.py::verify_access_token()`
calls Supabase Auth's `get_user(token)` rather than verifying the JWT's signature locally (which
would need the project's JWT signing secret held in the backend's own `.env`). **Why:** an
authoritative, instantly-revocation-aware check (a banned/deleted user's token stops working
immediately, not just at its natural expiry) with one fewer sensitive credential for the backend to
hold and rotate. The extra network hop's latency is negligible for a single WebSocket handshake and
one `/me` call, not a high-QPS API.

**Token sent as the first WebSocket message, not a `?token=` query param; distinct close codes.**
`/ws` requires an `{"type": "authenticate", "access_token": ...}` message before anything else, and
closes with **4401** on a bad/expired token or **4503** if Supabase Auth itself is unreachable.
**Why not a query param:** query strings end up in server access logs, some proxies, and browser
history — a message sent over an already-established connection doesn't. **Why two close codes, not
one:** a future frontend can tell "your session is invalid, log in again" (4401) apart from "retry
shortly, this isn't your fault" (4503) instead of treating every rejection as a forced logout.

**Token-refresh handling.** Supabase silently mints a new access token in the background before the
old one expires and fires `TOKEN_REFRESHED` via `onAuthStateChange`. Rather than reconnecting the
WebSocket on every refresh (which would interrupt an in-progress recording), the frontend re-sends
`authenticate` with the fresh token over the *same* open connection; the backend's `_authenticate`
handler explicitly supports re-authenticating as the same user in place (only a different user is
rejected). This is also directly exercised by KAN-18/KAN-19's acceptance criteria: a recording still
running past the JWT's expiry must keep persisting, not silently start dropping messages.

**Legacy (pre-auth) rows deleted, not migrated.** `003_auth_and_rls.sql` deletes every `sessions` row
with no `user_id` (cascading to `messages`) before making the column `NOT NULL`. **Why:** those rows
predate the concept of "user" entirely (Phase 0-2 manual/echo/STT-smoke-test sessions) — there is no
real owner to attribute them to, and inventing a migration path for ownerless data has no value here.

**Password reset: deferred, not built.** Supabase Auth supports `resetPasswordForEmail` plus a
redirect-based reset page, but that needs an email template and a dedicated page — extra surface
area with no payoff yet for a single-developer local project where the developer already knows their
own password. Straightforward to add later using supabase-js's existing support if this ever needs
more than one real user.

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
