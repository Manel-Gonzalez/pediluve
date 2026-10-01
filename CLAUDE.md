# Pédiluve — instructions for Claude Code

Read this before doing anything in this repo.

## What this project is

Real-time speech transcription + translation app, running locally. Browser captures raw PCM mic audio and streams it continuously over WebSocket to a FastAPI backend, which proxies it to ElevenLabs' realtime STT WebSocket, calls DeepL (translation), and persists to Supabase. See `README.md` for the full architecture diagram.

This is a portfolio project. Code quality and clear structure matter more than speed. It will be shown to recruiters.

## Stack (do not change without asking)

- **Frontend:** React 18 + Vite + TypeScript. Plain CSS or Tailwind — no component libraries unless asked.
  Icons from `lucide-react` (approved in Phase 5.5). Light/dark theme through semantic color tokens
  (`canvas`, `surface`, `fg`, `muted`, `primary`… in `tailwind.config.ts` + `index.css`) — use those,
  never raw `ink-*`/`accent-*` steps, in components.
- **Backend:** Python 3.11+ + FastAPI + `websockets`. Use `uvicorn` for dev.
- **STT:** ElevenLabs Scribe **realtime** (`scribe_v2_realtime`, `wss://api.elevenlabs.io/v1/speech-to-text/realtime`). Backend proxies: browser streams raw PCM to our own `/ws`, backend forwards it to ElevenLabs' WebSocket and relays `partial_transcript`/`committed_transcript` events back. No diarization on this endpoint — REST batch (`scribe_v2`) is the fallback if we ever need speaker separation.
- **Translation:** DeepL API Free tier.
- **TTS:** ElevenLabs (Phase 5 only), single fixed voice (`ELEVENLABS_VOICE_ID`) — no per-language voice mapping in v1.
- **DB:** Supabase (PostgreSQL). Use the `supabase-py` client. Schema in `supabase/migrations/`.
- **Auth:** Supabase Auth (Phase 3 only), email + password. No other provider (no OAuth, no magic link) in v1.
- **Routing:** React Router, introduced in Phase 3 (`/login`, `RequireAuth`-guarded routes) — Phase 4 adds routable per-session URLs on top of the same router rather than introducing one from scratch. No routing before Phase 3.
- **Audio capture:** Web Audio API + `AudioWorklet`, raw PCM (`pcm_16000` or whatever the browser's `AudioContext` actually negotiates). No `MediaRecorder`/WebM, no `pydub`/`ffmpeg` — ElevenLabs realtime needs uncompressed audio, so there's no container to convert.
- **Sharing:** a QR code / share link (`qrcode` on the frontend) gives anyone a read-only live view of a session at `/view/:shareToken`, no account needed — see `docs/decisions.md`'s "Phase 5: QR code live viewer" entry (D1–D6) for the full architecture.

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
│   │   ├── components/    ← AuthForm, Nav, RequireAuth (route guard), NewSessionModal,
│   │   │                    TranscriptRow (shared by the live view and history), SessionListRow,
│   │   │                    SharePanel (QR + copy link), PlayButton, AddToMySessions (guest),
│   │   │                    Button, IconButton, Dialog, ConfirmDialog, ThemeToggle, LogoMark,
│   │   │                    StatusPill (Phase 5.5 primitives)
│   │   ├── hooks/         ← useWebSocket (join_session/pause-resume aware), useMicrophone,
│   │   │                    useAuth (AuthProvider), useLiveViewer (/ws/view), useAudioPlayer,
│   │   │                    useLiveListen ("Listen live" queue), useTheme, useStickToBottom
│   │   ├── pages/         ← LoginPage, HomePage (sessions list + "New session"), LiveSessionPage
│   │   │                    (/sessions/:id/live), SessionDetailPage (/sessions/:id, read-only),
│   │   │                    ViewLiveSessionPage (/view/:shareToken, anonymous, outside RequireAuth)
│   │   ├── lib/           ← api client (REST + ApiError), types, auth/languageControls/
│   │   │                    recording/sessions/sessionTitle/routes/share/download/liveTranscript,
│   │   │                    theme/languageLabel/pagination/relativeTime/authForm/viewerState/
│   │   │                    liveStatus/autoScroll helpers
│   │   ├── audio/         ← pcm-worklet.js (AudioWorkletProcessor)
│   │   ├── App.tsx        ← route table only (RequireAuth + pages/)
│   │   └── main.tsx       ← AuthProvider + BrowserRouter wiring
│   ├── package.json
│   └── vite.config.ts
├── backend/
│   ├── main.py            ← FastAPI app, WebSocket + REST routers
│   ├── routers/           ← ws.py (owner: join_session/pause-resume, publishes into its
│   │                        live room), viewer_ws.py (anonymous /ws/view, KAN-50), me.py
│   │                        (GET /me), sessions.py (REST CRUD, on-demand translate,
│   │                        guest add/remove, transcript download), live_audio.py
│   │                        (GET /api/live-audio/{token}, fresh TTS clips, KAN-87)
│   ├── services/
│   │   ├── elevenlabs.py  ← realtime STT session + synthesize() (TTS)
│   │   ├── deepl.py       ← translate() + translate_many() (batched re-translation)
│   │   ├── live_rooms.py  ← in-memory LiveRoom/LiveRoomRegistry fan-out for /ws/view (KAN-50)
│   │   ├── storage.py     ← Supabase Storage for cached TTS audio
│   │   ├── tts_cache.py   ← message_audio cache lookup/synthesize/upload orchestration
│   │   ├── live_audio.py  ← in-memory store for freshly synthesized clips (KAN-87)
│   │   ├── supabase.py
│   │   └── auth.py        ← verify_access_token (Supabase Auth)
│   ├── models/            ← Pydantic schemas (messages.py, viewer.py, sessions.py, auth.py)
│   ├── requirements.txt
│   └── .env               ← gitignored
└── supabase/
    └── migrations/
        ├── 001_initial.sql
        ├── 002_disable_rls.sql            ← superseded by 003, kept as history
        ├── 003_auth_and_rls.sql           ← sessions.user_id, RLS + owner policies
        ├── 004_nullable_target_language.sql  ← sessions.target_language nullable,
        │                                       unique(session_id, sequence) on messages
        ├── 005_share_token.sql            ← sessions.share_token (KAN-50)
        ├── 006_message_audio.sql          ← message_audio table, keyed by (message_id, language)
        ├── 007_message_audio_storage_bucket.sql  ← Storage bucket + owner-scoped RLS
        └── 008_session_guests.sql         ← session_guests table + add_session_guest RPC
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

**Phase 3:** user accounts. Supabase Auth, email + password — login/register/logout,
React Router introduced for `/login` + a `RequireAuth`-guarded app (see `docs/decisions.md` for why
routing moved here instead of Phase 4). Sessions and messages get scoped to the authenticated user
(`sessions.user_id`, RLS policies so a user only ever sees their own data). Comes before Phase 4
because "list of my past sessions" is meaningless without knowing who "I" am first.

**Phase 4:** session-first flow (see `docs/decisions.md` for the full reasoning behind each piece
below). Home page (`/`) lists the signed-in user's own sessions — the list is the CRUD: rename and
delete are row actions there, not on a detail page. A "New session" modal creates one by name via
`POST /api/sessions`, then opens its live view at `/sessions/:id/live`, where the WebSocket
`join_session`s that id rather than the connection implicitly creating one. **One session spans
multiple record/pause/resume cycles**: stopping only pauses (`sequence`/`committed_texts`/
`db_session_id` persist across pauses within the same visit); only a disconnect ends it
(`ended_at` — "last time a live view left this session," written once per visit). A past session's
full transcript is a separate read-only page at `/sessions/:id`, re-translating it to another
language for viewing **computed on demand, not persisted** (the original live-session translation
stays in `messages.translated_text`/`target_language` untouched).

**Phase 4.5:** first visual-design iteration. Tailwind CSS with a small design-token system
(`tailwind.config.ts`: an accent/neutral color scale, a type scale) instead of hand-written CSS per
component; every existing page and component migrated to it; the transcript view redesigned into
paired cards with language badges. No new functionality — a styling pass over what Phase 3/4 built.

**Phase 5:** two pieces of work, delivered together under KAN-50 (see `docs/decisions.md`'s "Phase 5:
QR code live viewer" entry, D1–D6, for the full architecture behind both):
- **QR code live viewer:** the owner's live session view shows a share link + QR code
  (`SharePanel`); anyone who opens it (`/view/:shareToken`, no account needed) sees committed lines
  translate live into their own chosen language, over a separate anonymous `/ws/view` endpoint that
  never touches Postgres directly — everything comes from an in-memory room the owner's own
  connection populates. A signed-in guest can "Add to my sessions" from that page to keep read-only
  access after the live session ends (owner-only for rename/delete/target-language, enforced by RLS).
- **TTS playback**, extended to cover the viewer, not just the owner: a "play" button per translated
  line → ElevenLabs TTS → audio generated once and cached in Supabase Storage, keyed by `(message,
  language)` so a viewer picking their own language never re-triggers a paid call for one already
  cached — one fixed voice for v1, not one per language.

**Phase 5.5:** second visual pass (KAN-73; see `docs/decisions.md`'s "Visual design" entry). Semantic
light/dark tokens with an OS-following toggle, redesigned login (password confirmation on register),
in-app confirm dialogs instead of `window.confirm`, icon actions, sessions paginated 10 per page, a
re-laid-out owner live page, and a mobile-first viewer (paused/not-started blur, session-ended
notice, auto-scroll). Styling/UX only, plus `total` on `GET /api/sessions`.

**Phase 6 (parked, exploratory only):** speaker labels if multiple audio inputs. No multi-channel
capture exists yet and there's no confirmed use case for it — start with a spike (is there a real
multi-mic scenario? is `use_multi_channel` viable, or REST batch the only path?) before committing
to implementation subtasks. Realtime STT has no diarization on its own. Also: further VAD tuning;
persisting the in-flight partial transcript (so pausing mid-utterance doesn't lose it) plus manual
edit/delete of a message's original text — see `docs/decisions.md` for why this isn't a quick
add-on.

## What NOT to do

- Don't add multi-tenant/org complexity — Phase 3 adds per-user accounts (Supabase Auth), not
  roles, teams, or admin features. Each user only ever sees their own sessions. Phase 5's guest
  access (KAN-59, "add to my sessions" from a share link) is a deliberate, narrow exception: one
  fixed read-only relationship, no roles table — see `docs/decisions.md`'s D6 before extending it
  into anything broader.
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

Phase 3 — user accounts, **merged to `main`** (PR #2): KAN-14 (`GET /me` + `verify_access_token`),
KAN-16 (per-user Supabase client, RLS-safe writes), KAN-18 (`/ws` authenticate handshake + auth
gate), KAN-15 (frontend `supabase-js` client, `AuthProvider`, `AuthForm`), KAN-17 (React Router
shell — `/login`, `RequireAuth`, `Nav`), and KAN-19 (`useWebSocket`
authenticate/refresh/close-on-signout). KAN-13 (migration `003_auth_and_rls.sql`) has been applied
to the real Supabase project, with RLS isolation confirmed against two real accounts (distinct
`user_id`s, each only seeing their own `sessions` rows).

Phase 4 — session-first flow, **merged to `main`** (PR #3): KAN-22 (migration
`004_nullable_target_language.sql` — nullable `sessions.target_language`, `unique(session_id,
sequence)` on `messages` — **applied** to the real Supabase project), KAN-21 (session
read/update/delete functions + Pydantic models in `models/sessions.py`), KAN-36 (`/ws`
`join_session`/pause-resume rewrite, `SESSION_NOT_FOUND_CLOSE_CODE` 4404), KAN-24
(`routers/sessions.py` REST CRUD), KAN-25 (on-demand `/translate` endpoint +
`deepl.translate_many`), KAN-23 (REST API client, `HomePage`), KAN-37 (`NewSessionModal`), KAN-38
(`LiveSessionPage` at `/sessions/:id/live`, `join_session`-aware `useWebSocket`), KAN-26 +
KAN-27 (read-only `SessionDetailPage` at `/sessions/:id`, including its own on-demand
re-translation control), and KAN-39 (rename/delete on `HomePage` rows). Backend tests (`pytest`)
and frontend tests (`vitest`) both passing in CI. **Verified end-to-end in a real browser**
against the real Supabase project (create → record → pause → resume → end → revisit → rename →
delete), migrations 003 and 004 both live.

Phase 4.5 — visual design, **merged to `main`** (PR #5): KAN-42 (Tailwind CSS + design tokens),
KAN-43 (`Nav`), KAN-44 (`AuthForm`, `NewSessionModal`), KAN-45 (`HomePage`), KAN-46
(`LiveSessionPage` + recording indicator), KAN-47/KAN-48 (transcript redesigned into paired cards
with language badges, applied to both the live view and `SessionDetailPage`). Verified in a real
browser (KAN-49).

Phase 5 — QR code live viewer + TTS, **merged to `main`** (PR #6): all 20 subtasks under KAN-50.
Three milestones:
- **Milestone A (viewer core):** KAN-51 (migration 005, `sessions.share_token`), KAN-52
  (`services/live_rooms.py` — `LiveRoom`/`LiveRoomRegistry`), KAN-53 (LAN reachability —
  `getApiUrl`/`getWebSocketUrl` derive their host from the page's own location, `vite.config.ts`
  `server.host: true`), KAN-54 (owner `/ws` publishes into its room, owner-only `join_session`
  guard), KAN-55 (anonymous `/ws/view` endpoint), KAN-56 (`ViewLiveSessionPage` at
  `/view/:shareToken`), KAN-57 (`SharePanel` — QR code + copy link on `LiveSessionPage`).
- **Milestone B (TTS playback):** KAN-28 (migration 006, `message_audio`), KAN-29 (real
  `elevenlabs.synthesize()`), KAN-30 (`services/storage.py`), KAN-31 (`services/tts_cache.py`),
  KAN-58 (viewer `request_audio` wired to the cache), KAN-32 (session delete cascades cached
  audio in Storage), KAN-33 (`PlayButton`/`useAudioPlayer` on the viewer page).
- **Milestone C (guests + download):** KAN-59 (migration 008, `session_guests` +
  `add_session_guest` `SECURITY DEFINER` RPC), KAN-60 (`POST /api/shared/guest`,
  `DELETE /api/sessions/{id}/guest`), KAN-61 (`GET /api/sessions/{id}/transcript` plain-text
  download), KAN-62 (`AddToMySessions` on the viewer page), KAN-63 (guest rows + badge on
  `HomePage`).

Migrations 005–008 are **applied** to the real Supabase project. **Verified end-to-end on real
devices**: owner recording on `localhost`, viewers on phones over the LAN via the QR code, live
translation into each viewer's own language, TTS playback (per line and "Listen live"), refresh
mid-session keeps the history, add as guest → guest row on `HomePage`, session ended, both
download buttons. Not tested on an iPhone, nor from outside the local network (local-only by
design). Real-device testing led to follow-up fixes and features on the same branch - see
`docs/decisions.md`'s "Phase 5: changes after real-device testing" entry. Backend tests
(`pytest`, 250) and frontend tests (`vitest`, 94) passing.

KAN-65 — live latency, **merged to `main`** (PR #8): ElevenLabs' VAD commit delay down to 1.0 s
(`ELEVENLABS_VAD_SILENCE_SECS`), the Supabase save moved off the line's critical path (viewer audio
requests wait for the pending `message_id`), and a `live_speaking` flag on `/ws/view` that shows a
"speaking" bubble on the viewer page. See `docs/decisions.md`'s KAN-65 entry.

KAN-66 — public demo through a temporary Cloudflare tunnel, **merged to `main`** (PR #9): the
frontend only talks to its own origin and the Vite dev server proxies `/api` and `/ws` to uvicorn,
so one tunnel to `:5173` is enough. Not a deployment - see `docs/decisions.md`'s KAN-66 entry and
README's "Public demo" section. Verified with a real tunnel and a phone on mobile data.

KAN-72 — README as a portfolio showcase, **merged to `main`** (PR #10). The demo GIF and
screenshots (`docs/media/`) are still to be recorded; their tags are commented out in the README
until then.

Phase 5.5 — visual redesign (KAN-73), **merged to `main`**: KAN-74 (light/dark tokens, theme
toggle, favicon), KAN-76 (lucide icons, Button/IconButton, language names), KAN-77
(Dialog/ConfirmDialog, no more `window.confirm`), KAN-75 (`total` on `GET /api/sessions`), KAN-78
(HomePage, 10 per page in a self-scrolling card, relative dates), KAN-79 (login redesign + password
confirmation), KAN-80 (viewer paused/not-started overlay, ended notice, clean final state), KAN-81
(owner live page + detail page, status pill, End session confirm), KAN-82 (viewer auto-scroll +
"new lines" chip). Romanian and Dutch added as spoken/translation languages on the same branch.
KAN-68/69/70 superseded; KAN-71 stays parked under KAN-67. Verified on real devices (PC + phone,
LAN and tunnel). Backend tests (`pytest`, 273) and frontend tests (`vitest`, 138) passing.

KAN-84 — the viewer's pause overlay can be closed (a slim status bar replaces it for the rest of
the visit, so earlier lines can be played during a pause), plus a "Recording resumed" toast. On
`feature/KAN-84`. Frontend tests (`vitest`, 145) passing.

KAN-85 — "Listen from here" on each viewer line: plays from that line to the latest, then carries
on live; audio prefetched two lines ahead instead of the whole queue. On `feature/KAN-85` (branched
from `feature/KAN-84`). Frontend tests (`vitest`, 151) passing.

KAN-86 — viewer "jump to latest" arrow whenever scrolled up (a count once lines arrive), and the
listening controls moved into the sticky header so they stay reachable on a phone. On
`feature/KAN-86` (branched from `feature/KAN-85`). Frontend tests (`vitest`, 154) passing.
Also on that branch: concurrent audio requests for one line share a single TTS generation.

KAN-87 — a fresh TTS clip goes to the listener as soon as ElevenLabs returns it, served from
memory by `GET /api/live-audio/{token}`; the Storage upload and `message_audio` row follow in the
background. WebSocket contract unchanged. On `feature/KAN-87` (branched from `feature/KAN-86`).
Backend tests (`pytest`, 291) passing.

Next: record the README demo GIF and screenshots. KAN-71 (owner-reload grace period) is the one
parked follow-up. Phase 6 stays parked - start with its spike (see Phase gates) only if a real
multi-mic use case shows up.
