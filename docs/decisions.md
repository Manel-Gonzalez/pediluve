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

## Phase 4: session-first flow

**Context:** a product-flow correction (see "Phase reorder" above for the shape of these
mid-project corrections) replaced the original Phase 4 assumption (a session created implicitly
the moment recording starts) with: a session is created explicitly, by name, from a "New session"
modal on the home page; the home page lists every session as a CRUD list (revisit, rename,
delete); and **one session spans multiple record/pause/resume cycles**, not a fresh session per
stop/start.

**Create-by-name via REST, not implicit create on start.** `POST /api/sessions` (KAN-24) is now
the only way a `sessions` row is created; `/ws`'s `_start_transcription` no longer calls
`create_session` at all (KAN-36) - a `create_session` call was removed from there and a test
(`test_start_transcription_never_calls_create_session`) added specifically to keep it removed.
**Why:** the whole point of the redesign is that a session is a named thing the user chooses to
start ("imagine a meeting: you name it, then you record into it"), not a byproduct of pressing a
mic button. REST is also just the natural fit for "create, then navigate to the new resource's
URL" - a WebSocket message has no equivalent to "the browser navigates to
`/sessions/<new-id>/live`" without extra plumbing. **Revisit if:** a "start recording immediately,
name it later" flow is ever wanted (e.g. a walk-up dictation use case) - a session would need an
initial placeholder title, and `_start_transcription` would need to create one again.

**One session, many record cycles.** `start_transcription`/`stop_transcription` changed meaning
from create/end to resume/pause (KAN-36): stopping no longer ends the session - only a real
disconnect does. `sequence`, `committed_texts`, and `db_session_id` are all seeded once by
`join_session` and carry across every pause/resume in the same visit, instead of resetting per
recording. **Why:** matches the mental model directly - a meeting has one transcript, however many
times recording is paused and resumed during it, not one transcript per unpause. **Revisit if:** a
use case needs *separate* transcripts within one "meeting" (e.g. distinct agenda items) - that
needs an explicit sub-session or section concept, not just more pause/resume cycles on one
`sessions` row.

**`join_session` as its own WS message, not a query param or folded into `authenticate`.**
Considered: `?session_id=` on the WS URL, or adding `session_id` to the `authenticate` payload.
**Why `join_session` won:** a query param on the WS URL would put the session id in server access
logs, the same reasoning already given above for sending the JWT as a message rather than a query
param; folding it into `authenticate` conflates two independent concerns (who you are vs. which
session this connection is for), and would make re-authenticating on token refresh awkwardly also
re-specify the session every time. A separate message keeps `authenticate` unchanged and makes
"authenticated but not yet joined" a real, representable state - the frontend uses exactly that
state (`joinStatus`) to disable Start/target-language controls until `session_joined` arrives.
**Revisit if:** a connection ever needs to join more than one session at once - not a current use
case, since one WS connection is one live view.

**4404 as the "session not found" close code.** `SESSION_NOT_FOUND_CLOSE_CODE = 4404` covers an
unknown id, a non-UUID id, and someone else's id under RLS - all three look identical to the
client, since RLS makes "not yours" and "doesn't exist" indistinguishable at the DB layer (the
same reasoning the REST 404 mapping below relies on). **Why a new code, not reusing 4401:** 4401
already means "authentication problem, log in again" (KAN-18) - conflating "your session id was
wrong" with "your login was wrong" would send the user down the wrong recovery path, since
re-logging in doesn't fix a bad link. **Revisit if:** the close-code space needs auditing again -
4401/4404/4503 are all in the private range (4000-4999), picked to avoid colliding with any
registered WebSocket close code.

**REST 404 for a malformed id too, not FastAPI's default 422 or a raw 500.** `routers/sessions.py`
validates `{id}` is a UUID in-route before ever querying Supabase, mapping a bad UUID straight to
404. **Why:** a garbage id (`/api/sessions/not-a-uuid`) is exactly as "not found" from the caller's
perspective as a well-formed UUID for a row that doesn't exist or isn't theirs - three
different-looking failures (422 for a bad shape, 500 for a raw Postgres error on the UUID cast, 404
for a real miss) would need three different handling paths in the frontend for what is, to the
user, one outcome: "that link doesn't work anymore." One response shape means one place to handle
it - `ApiError(404)` → "Session not found" + a link home, on both `LiveSessionPage` and
`SessionDetailPage`. **Revisit if:** a caller ever needs to tell "malformed" apart from "real miss"
(e.g. to log obviously-forged ids differently) - that's a case for a distinct error code in the
response body, not a different HTTP status.

**Pagination: `limit`/`offset` with a `has_more` flag, not a total count.** `GET /api/sessions`
fetches `limit + 1` rows to know whether there's a next page, rather than running a separate
`COUNT(*)` query. **Why:** a session list is browsed, not jumped-to-page-N - "is there more" is all
"Load more" needs, and a second count query would double the DB round trips for a number the UI
never displays. `limit` is clamped server-side to 100 regardless of what's requested, so a client
bug (or a tampered request) can't force an unbounded fetch. **Revisit if:** the UI ever wants a
numbered pager or a "showing X of Y" count - that needs the real total, which is the point where
the extra `COUNT(*)` query becomes worth its cost.

**Pause vs. "End session."** The live view's mic button is Start → Pause → Resume (never Stop); a
separate "End session" button explicitly leaves the live view and navigates home. **Why a separate
action, not overloading Pause:** per "one session, many record cycles" above, pausing must not end
the DB session - but the user still needs a clear, deliberate way to say "I'm done with this
meeting" and leave, distinct from "I'm just pausing to let someone else talk." One button for both
would mean either pausing accidentally ends the session, or leaving the page requires knowing to
pause first. **Revisit if:** user testing shows the two actions get confused for each other - a
single button with a confirm step is the likely fix, not re-merging the two actions.

**`ended_at` now means "last time a live view left this session," not "recording finished."** It's
written exactly once per visit, in `_cleanup` on disconnect - never in `_pause_transcription`,
never on every stop (KAN-36). **Why:** the earlier meaning ("this session is over") stopped being
true the moment resume became possible - a session can be revisited (a fresh WS connection,
a fresh `join_session`) after `ended_at` was already set, and that reconnect correctly overwrites
it again on the next disconnect. **Revisit if:** a genuine "this session is permanently closed"
state is ever needed (e.g. to block further recording into an old session) - that's a different
column (an explicit `closed` flag), not a repurposing of `ended_at` again.

**The "unfinished" badge was dropped, not built.** An earlier reading of the spec assumed the home
list would flag a session with `ended_at IS NULL` as "unfinished," implying it stopped
mid-recording (e.g. a crash). **Why dropped:** now that pausing deliberately leaves `ended_at` null
until the *next* disconnect (see above), a null `ended_at` no longer distinguishes "abandoned
mid-recording" from "perfectly normal, currently paused, might be resumed any time" - the signal
the badge was meant to carry doesn't exist under the new semantics. **Revisit if:** a real "was
this actually abandoned" signal is wanted - that needs its own explicit state, not an inference
from `ended_at`.

## Phase 4: re-translating a past session's history is on-demand, not persisted

**Context:** KAN-10's history view lets a user open a past session and view it translated into a
language other than the one it was originally recorded with. `messages.translated_text`/
`target_language` already hold the live-session translation from when it was recorded.

**Chosen:** `POST /api/sessions/{id}/translate` calls DeepL fresh every time the view is opened in a
new language and returns the result without writing anything back - the original
`messages.translated_text`/`target_language` stay exactly as recorded. **Why:** persisting every
language a session has ever been viewed in would need a join table (`message_id`, `language`,
`translated_text`) for a feature that's read far more rarely than it would be written, and it
would let stored translations silently go stale if DeepL's model changes. On-demand keeps the
schema as-is and the history view always reflects DeepL's current output.

**Cost:** viewing a session's history in a language it hasn't been viewed in before spends DeepL
characters again, every time - on the free tier's monthly quota, repeatedly opening old sessions in
several languages adds up. Not a problem yet at single-user local-only scale; worth revisiting
(e.g. a short-lived cache) if this ever runs with real usage volume.

**Batching:** `deepl.translate_many()` sends up to 50 texts as repeated `text` fields in one DeepL
request rather than one request per message - a session with dozens of messages would otherwise be
dozens of sequential round trips just to open the page. Chunks beyond 50 (DeepL's per-request limit
is unconfirmed from this sandboxed environment, same restriction noted above for Catalan) go in
further requests; a failed chunk maps to `null` for each of its messages rather than failing the
whole view; a still-untranslated `original_text` is a legitimate result, not a bug to hide.

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

## Phase 5: QR code live viewer (KAN-50)

**Context:** the original Phase 5 plan was TTS playback only. Partway through, a new idea landed:
let anyone scan a QR code and watch a session's transcript translate live, in their own language, on
their own phone, with no account - a much stronger portfolio demo than a solo screen recording.
Approved scope for this work: **live viewing only** (a past/ended session isn't shareable this way),
**no diarization/speaker separation** (out of scope, unrelated to this feature), and **TTS playback
extended to the viewer** rather than staying owner-only. Six decisions shaped the implementation,
labelled D1-D6 below since earlier planning notes and code comments (`routers/viewer_ws.py`,
`services/live_rooms.py`, the migrations) refer to them by these labels.

**D1 - a separate `/ws/view` endpoint, not a new message type on `/ws`.** `/ws`'s safety today is one
gate (`self.user is None`) in front of every owner capability (STT spend, `set_target_language`,
ending the session). Adding a "viewer" identity to that same handler would need a role check on
every current *and future* branch there - one missed check is a privilege escalation. A separate
handler (`routers/viewer_ws.py::ViewerConnectionHandler`) makes the boundary structural instead of a
habit to remember.

**D2 - the share token travels as the first WS message (`join_live`), never in the WS URL.** Same
log-hygiene reasoning as `/ws`'s own `authenticate`/`join_session`. It's unavoidably in the *page*
URL `/view/<token>` - that's the whole point of the QR code - so it's a bearer capability link by
design: anyone who has the link can view, and the token is deliberately not distinguishable from
"session isn't live right now" on a bad guess (`routers/viewer_ws.py`'s `LIVE_NOT_AVAILABLE_CLOSE_CODE`).

**D3 - anonymous viewers never touch Postgres.** Everything a viewer sees comes from an in-memory
`LiveRoom` (`services/live_rooms.py`), populated entirely by the *owner's own* connection: its own
RLS-scoped `join_session` read, its own committed lines, its own translation calls. A token-to-room
lookup is a plain dict read; only owner connections ever write to that registry. Rejected: a
token-keyed RLS policy (makes query security depend on parsing a header, and grants the `anon` role
table access it doesn't need), Supabase Realtime for viewers (needs `anon` SELECT on `sessions`/
`messages`), a service-role read (breaks the "never use the service-role key" invariant this project
holds everywhere else). The direct consequence, and the reason viewing is live-only for v1: a room
only exists while at least one owner connection for its session is live.

**D4 - fan-out is a queue, never inline.** One `LiveRoom` per session, refcounted by owner
connections (closes when the last one disconnects). The owner's committed-transcript path calls
`room.publish(...)` (a non-blocking `put_nowait`) right after its own Supabase save - never awaited,
never doing translation or viewer I/O itself. A single room worker task drains that queue in order:
computes the distinct viewer languages currently connected, translates only what's missing via
`asyncio.gather` (one DeepL call per language, not per viewer), caches results per line, then sends
to each viewer with a per-send timeout that drops a slow/failed one rather than blocking the rest.
The owner's own translation seeds the cache for its own language, so a viewer who happens to match it
costs nothing extra. Net effect: a stalled or malicious viewer connection can never slow down the
owner's own transcript, and total DeepL spend per room is bounded by lines × distinct languages, not
lines × viewers.

**D5 - TTS cache keyed by `(message_id, language)`, not the one-`audio_path`-column design KAN-28
originally sketched.** A viewer picks their own display language independently of the session's own
`target_language`, so caching only the canonical language would let anyone holding a QR link trigger
unbounded ElevenLabs spend just by switching languages and clicking play (lines × language switches ×
viewers). The `message_audio` table (migration 006) and `services/tts_cache.py` fix the unit cost at
one ElevenLabs call per `(message, language)` ever, cache hits after that. Storage objects live at a
deterministic, owner-prefixed, flat-per-session path
(`{owner_id}/{session_id}/{message_id}.{language}.mp3`, `services/storage.py`) so
`delete_session_audio`'s cleanup on session delete (KAN-32) stays a single-level Storage `list`, and
`storage.objects` RLS (migration 007) is a plain `auth.uid()` check against the path's first segment.
A viewer's `request_audio` borrows the *live owner connection's own JWT* (`LiveRoom.owner_user`,
refreshed on every re-authenticate) to actually write that cache - an anonymous viewer has no
Supabase identity of its own to write with.

**D6 - guests are added via a `SECURITY DEFINER` RPC, not a plain INSERT policy.** "Add to my
sessions" (KAN-59-KAN-63) needed a `session_guests` row, but every browser already holds the anon key
plus the signed-in user's own JWT and can call PostgREST directly - a policy shaped like `user_id =
auth.uid()` would let *any* signed-in user add themselves as a guest to *any* session id, since a
declarative RLS policy can't also verify the caller holds that session's actual `share_token`. Only a
function can do both checks (`add_session_guest(share_token, target_language)`, migration 008):
resolve the session from the token itself, then force `user_id = auth.uid()`, never a caller-supplied
value. `search_path = ''` plus fully schema-qualified names close off the classic search-path-hijack
attack on `SECURITY DEFINER` functions; `execute` is revoked from `anon`/`public` and granted only to
`authenticated`. This is the deliberate, narrow exception to `CLAUDE.md`'s "don't add multi-tenant/
org complexity" rule - one fixed, read-only relationship (a guest reads a session and its messages,
nothing else), no roles table, no admin features. Rename/delete/target-language changes stay
owner-only at the RLS layer regardless of what the application code does.

**Not done in this pass:** diarization/speaker separation (never in scope for this feature - see
Phase 6 below for the actual spike), TTS playback on the owner's own live/history views (`request_audio`
only exists on `/ws/view`; adding it to owner `/ws` or as a new REST endpoint wasn't part of the
approved scope for this week).

## Phase 5: changes after real-device testing (KAN-50)

The first real run (owner on a laptop, viewers on phones over the LAN) surfaced issues the unit tests
couldn't, plus a few UX changes. Recorded here because each one changed a design assumption above.

- **The owner records on `localhost`; the QR link uses `VITE_SHARE_BASE_URL`.** `getUserMedia` only
  exists in a secure context (`localhost` or https), so an owner opening the app at its LAN IP has
  no mic at all. But a QR code built from `localhost` sends the phone to itself. The share link's
  base URL is therefore configurable (`lib/share.ts`) and set to the machine's LAN origin, while
  the owner stays on `localhost`.
- **Storage calls carry the user's JWT, not the anon key.** supabase-py builds `client.storage`
  from `client.options.headers`, not from the PostgREST auth that `client_for` was setting, so
  every upload ran as `anon` and hit the bucket's RLS. `client_for` now sets both. The fakes in
  the tests had modelled the client wrongly, which is why only real Supabase caught it; a test
  now asserts on a real client's Storage headers.
- **A live room is seeded with the session's stored history.** A room started empty, so a viewer
  who refreshed mid-session (or joined late) lost every earlier line. The owner's `join_session`
  already reads the full history under its own RLS, so `LiveRoom.seed_history` loads it into the
  room: still no viewer ever touches Postgres (D3). For the same reason a guest who saved a session
  and left halfway sees the complete session afterwards: a guest row points at the live original,
  never at a snapshot.
- **The viewer shows only the translation**, since it's meant for phones. Its "Download
  translation" builds the file client-side from lines already in memory, because an anonymous
  viewer has no Supabase session to call the authenticated transcript endpoint with.
  `SessionDetailPage` uses that endpoint instead.
- **A guest's saved session opens in the guest's own language** (`session_guests.target_language`,
  translated on demand as in Phase 4), not the owner's.
- **"Listen live" reads new lines aloud as they arrive** (`hooks/useLiveListen.ts`). It starts from
  the next line, not the backlog: reading everything said so far would leave the listener
  permanently behind (KAN-85's "Listen from here" is the opt-in exception, below). Audio is
  requested a little ahead of each line's turn, so the next one is generated while the current one
  plays. Per-line Play buttons are hidden while it's on, so a
  manual tap can't cut into the queue. Playback goes through one reused `<audio>` element,
  unlocked with a silent clip inside the tap that starts it, because iOS Safari blocks `play()`
  calls that don't come from a user gesture.
- **The backend runs with `--timeout-graceful-shutdown 3`.** On Windows, uvicorn hung forever at
  "Shutting down" while a phone's `/ws/view` socket was open; the timeout bounds that wait.

## Live latency: shorter VAD silence, save off the critical path, "speaking" flag (KAN-65)

Real-device testing showed a line appearing about 2 s after the speaker stopped. Three changes:

- **ElevenLabs' VAD commit delay went from 1.5 s (their default) to 1.0 s**, sent as
  `vad_silence_threshold_secs` and overridable with `ELEVENLABS_VAD_SILENCE_SECS` (ElevenLabs accepts
  0.3-3.0). 1.0 s still rides out a half-second hesitation; lower values split sentences at short
  pauses, which also costs DeepL context and gives "Listen live" more, shorter fragments.
- **The Supabase save no longer sits between translation and the send.** A committed line used to go
  DeepL, then save, then send. The save now runs alongside the send and the room publish, and the
  transcript worker still awaits it before the next line, which keeps `sequence` ordered and keeps
  the "still persisted after a disconnect" guarantee. The catch: a viewer can see a line before its
  `message_id` exists, and "Listen live" requests audio the moment a line arrives. So a room line
  holds the pending save itself, and `request_audio` waits on it: capped at 10 s, and shielded so a
  viewer's timeout can't cancel the owner's save.
- **Viewers get a `live_speaking` flag.** They only ever see committed, translated lines, so while
  the owner talks their screen sat still. The owner raises the flag on a sentence's first non-empty
  partial and lowers it after that sentence's line is published, when the commit turns out to be
  noise, or on pause. Sending partial *text* was rejected: viewers see translations only, and
  translating every partial would multiply DeepL calls. The flag goes through the room's line
  queue, not straight to viewers, so "stopped speaking" can never overtake its own line.

## Public demo: one tunnel, same-origin frontend (KAN-66)

**Context:** showing the app to someone outside the LAN for a few minutes (a recruiter on their own
phone), a few days before an interview. `CLAUDE.md` says local only, and a real deployment (Render/
Fly/Vercel, or InstaCloud, which was looked at) would mean Docker or a hosted backend, a second place
for secrets, and open sign-up exposed to paid APIs. It also wasn't worth that risk days before a demo.

**Decision:** a Cloudflare Quick Tunnel (`cloudflared tunnel --url http://localhost:5173`) while the
demo runs. Nothing is deployed; the URL dies with the command. To need one tunnel instead of two:

- **The browser only talks to its own origin.** `lib/api.ts` used to call uvicorn at
  `<page host>:8000`, so every way of reaching the app needed that port open and listed in
  `CORS_ORIGINS`. Now the Vite dev server proxies `/api` and `/ws` to uvicorn, and uvicorn only has
  to listen on `localhost`. `VITE_API_URL`/`VITE_WS_URL` still override for a backend outside that
  proxy.
- **Vite allows `*.trycloudflare.com`** (Vite rejects unknown `Host` headers by default).
- **The QR uses the page's own origin unless it's `localhost`.** Over the tunnel's https the mic
  works, so the owner can record from the tunnel URL and the QR carries it.
  `VITE_SHARE_BASE_URL` now only fills the one gap it was for: an owner on `localhost` sharing
  with the LAN.

**Risk accepted:** while the tunnel is up, the app is public. Mitigations are operational, not code:
turn off Supabase sign-ups for the demo and stop the tunnel afterwards (README).

## Visual design: Phase 4.5 tokens, Phase 5.5 redesign (KAN-73)

**Context:** Phase 4.5 moved every component to Tailwind with a small token scale (`accent`, `ink`),
but components still used raw steps (`text-ink-900`, `bg-accent-500`). There was no dark mode.
Browser `confirm()` boxes, text-only buttons and debug text ("WebSocket status: authenticated") were
still on screen. Phase 5.5 is a second pass before showing the app to recruiters. It is a styling/UX
pass only, apart from `total` on the session list. References: Vercel Geist, shadcn/ui theming,
Linear, Raycast, Granola, and Apple Live Captions for the viewer.

- **Semantic tokens backed by CSS variables, not `dark:` pairs.** Components use `canvas`,
  `surface`, `subtle`, `line`, `fg`, `muted`, `primary`, `highlight` and `danger`. Each is
  `rgb(var(--x) / <alpha-value>)`, defined once under `:root` and once under `.dark` in `index.css`.
  One place per theme instead of a `dark:` variant on every element, and opacity modifiers still
  work. Primary moved from accent-500 to accent-600: white on accent-500 failed WCAG AA (3.1:1).
- **Theme: the OS setting until the user picks one.** `darkMode: 'selector'`, with an inline script
  in `index.html` that sets the class before first paint, so there is no white flash. An explicit
  choice is kept in localStorage (`pediluve-theme`). Without one, the page follows OS changes live.
  The rules live in `lib/theme.ts`, which is tested, and the inline script mirrors them.
- **Native `<dialog>` for modals.** `showModal()` provides the top layer, an inert background and
  a focus trap. `Dialog` adds backdrop-click, initial focus and returning focus to the opener, and
  `ConfirmDialog` is built on it. A failed action stays inside the dialog instead of failing
  silently.
- **`lucide-react` for icons** (approved new dependency) over hand-copied SVG paths. It is
  tree-shaken, about 1 KB per icon. Every icon-only button goes through `IconButton`, which
  requires a label (used for `aria-label` and the tooltip).
- **Pagination: 10 per page, offset-based, page in the URL.** `GET /api/sessions` now also returns
  `total` (`count="exact"`, KAN-75), for "Page 2 of 7". `?page=N` survives reloads and Back, an
  out-of-range page is clamped, and removing the last row of the last page steps back one page. The
  rejected alternative was keeping "Load more", which was the explicit complaint (no endless list
  with 100 sessions).
- **"Not started" vs "paused" on the viewer.** A live room starts `paused` until the owner first
  records, so a paused state alone would tell a viewer who scanned early that the speaker is on a
  break. `viewerControls()` uses `seenRecording`, or existing lines from a resumed session, to
  choose between the two messages. The blur covers only the transcript: the language, Listen live
  and download controls stay usable. No WebSocket contract change was needed.
- **The pause overlay can be closed (KAN-84).** Found on a real phone: during a pause is exactly
  when a viewer wants to replay an earlier line, and the blur sat on top of its Play button. Closing
  it once holds for the rest of the visit: the wait becomes a slim bar inside the sticky header
  (`viewerControls()`'s `statusBar`), and a "Recording resumed" toast (`role="status"`, about 4 s)
  says when the owner presses record again. `recordingNotice()` only fires on a paused→recording
  change the viewer sat through, so arriving mid-recording shows nothing. The dismissal is
  component state, not `localStorage`: a reload, or a new session, starts with the overlay again.
- **"Listen from here" (KAN-85).** A second button per line starts the Listen live queue at that
  line instead of at the next new one: it and every line after it play in order, then new lines
  carry on live. "From the start" is that button on the first line, so it's one control, not two.
  The rejected alternative was a separate "play transcript" player alongside Listen live: two
  queues sharing one `<audio>` element would have to coordinate, for no gain. Starting early
  while the owner records leaves the listener behind live by about the backlog's reading time;
  that's the listener's choice, and Listen live goes back to live.
- **Audio is prefetched two lines ahead, not the whole queue (KAN-85).** Listen live used to request
  every queued line's audio at once. That was fine for one or two new lines, but a catch-up from
  line one of a long session would fire dozens of ElevenLabs calls together. That would spend
  credits on lines the listener may never reach and could hit the plan's concurrency limit.
  `audioToRequest()` asks only for the line playing plus the next two; cached lines cost nothing.
- **A way back to the latest line that's always there (KAN-86).** The view follows new lines unless
  the reader scrolled up (KAN-82), but the only way back was the "N new lines" chip, which only
  appeared once a line arrived; during a pause there was none. Now a round arrow shows as soon as
  the reader scrolls up, and it becomes the count when lines arrive (`jumpControl()`). Tapping
  either pins the view again.
- **The viewer's controls live in the sticky header (KAN-86).** On a phone, Listen live, the
  language, Save and Download scrolled out of reach down a long transcript. They now sit in a
  second header row. That costs about 50px of a phone screen, but the header is translucent and
  these are the page's only actions. Below 380px "Save" goes icon-only, so the language picker
  keeps its room. When the session ends, the row goes and the ended notice takes its place, in
  the page as before.
- **The audio unlock must play out (KAN-86 fix).** On a phone, Listen live skipped its first line.
  KAN-85's `start()` called `stop()` right after `unlock()`, which aborted the silent unlock
  clip, so the first real `play()` could be refused. `stop()` now runs first. The shared
  `<audio>` element also ignores an `ended` event unless `audio.ended` is true. A late one from a
  replaced track (the unlock clip, as the first line starts) would otherwise count as that line
  finishing.
- **The pause card is centred on the screen, not the transcript.** It sat at the top of the
  blurred transcript, off-screen once a phone had scrolled down. It's now `fixed` and centred,
  as a sibling of the blur rather than inside it, because `backdrop-filter` would make the blur
  its containing block.
- **One audio generation per (line, language) at a time (`services/tts_cache.py`).** Found in a
  real test with three listeners in Spanish: two asked for a new line's audio at the same
  moment. Both missed the cache, so both paid for an ElevenLabs call and uploaded to the same
  path. The second upload is an overwrite, which Storage RLS refuses because migration 007 has
  no UPDATE policy. That listener got "Audio unavailable" and Listen live skipped the line, at
  random. Concurrent misses now await one shared generation, shielded so a listener leaving
  doesn't cancel it for the rest. A failure isn't remembered, so the next request tries again.
  The rejected alternative was an UPDATE policy: it would stop the error but still pay for every
  duplicate call. In-process is enough because every room lives in this one uvicorn process.
- **Every animation behind `motion-safe:`**, including the recording ping, the speaking dots, the
  login hero's waveform and the smooth auto-scroll.

## Future: persisting partial transcripts + manual edit (parked, Phase 6+)

**Context:** Manel's idea, while verifying Phase 4 by hand: if you pause right as you're mid-sentence,
the in-flight `partial_transcript` is lost — only a `committed_transcript` (ElevenLabs' own "this
segment is final" signal) ever reaches `_handle_committed_transcript` and gets saved. Proposal: save
the partial too, marked as such, so an accidental pause doesn't lose it; a further idea in the same
vein is letting a user manually edit or delete part of a message's original text later.

**Why this is parked, not a quick add-on:**
- Partials fire many times a second while speaking (each is ElevenLabs revising its own guess at the
  current segment) - naively inserting a `messages` row per partial would flood the table. This needs
  an upsert-the-latest-partial-into-one-row model, not the existing append-only insert path.
- ElevenLabs already sends an `edited_transcript` event when it revises a previously-committed
  segment - today `_relay_transcripts` only logs it (`elif event_type in ("session_started",
  "warning", "edited_transcript"): logger.info(...)`). That event is the most likely mechanism for
  "partial became final, replace its row" - worth investigating before designing a custom
  reconciliation scheme, rather than assuming one is needed from scratch.
- Needs a schema change (a `status`/`is_partial` column on `messages`, or a separate table) and a WS
  contract change (a new message type, or a status field on the existing `transcript` message) -
  exactly the two things `CLAUDE.md`'s "ask before" list flags, so this isn't a fix folded into
  whatever ticket happens to touch `_handle_committed_transcript` next.
- Manual edit/delete of `original_text` raises its own follow-on questions this hasn't been scoped
  for yet: does editing a message re-trigger translation (spends DeepL quota) or just update the
  displayed original, and does `sequence` stay stable under a delete (almost certainly yes, per the
  reasoning `messages_session_sequence_unique` was added for - see KAN-22 above).

**Revisit:** scope it as its own planned piece of work (`plan-task`) once there's appetite to build
it - candidate for Phase 6 alongside the other parked items, not a Phase 4/5 blocker.

## Future: production deploy on AWS (not started, notes for later)

**If this ever needs to run in production:**

- **Backend: ECS Fargate, not Lambda.** The WebSocket connection stays open while audio chunks stream in. Lambda + API Gateway WebSocket would mean every message is a separate invocation, with connection state pushed into DynamoDB between them — a lot of rearchitecting for a project this size. Fargate keeps the current always-on FastAPI process model.
- **DB: RDS Postgres instead of Supabase.** Same schema, same SQL migrations in `supabase/migrations/`, just a different connection string. No need for DynamoDB or Aurora.
- **Frontend: S3 + CloudFront**, built as a static Vite bundle, fully decoupled from the backend.
- **Repo stays a monorepo.** Two GitHub Actions workflows with path filters (`frontend/**`, `backend/**`) build and deploy each side independently — no need to split into separate repos for this.

**Revisit:** only if/when an actual deploy is planned. Phase 0-5 stay local-only per `CLAUDE.md`.
