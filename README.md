# Pédiluve 🎙️

[![CI](https://github.com/Manel-Gonzalez/pediluve/actions/workflows/ci.yml/badge.svg)](https://github.com/Manel-Gonzalez/pediluve/actions/workflows/ci.yml)

**Speak in your language. Everyone in the room reads it, or hears it, in theirs, live on their own phone.**

Pédiluve transcribes speech as you talk, translates each sentence, and shares the session through a
QR code. Anyone who scans it follows along in the language they pick, with no account and no app to
install, and can have each new line read aloud as it arrives.

<p align="center">
  <img src="docs/media/demo.gif" alt="Speaking on a laptop while a phone shows each sentence translated live" width="800">
</p>

## What it does

- **Live transcription**: raw mic audio streams to ElevenLabs' realtime speech-to-text; text shows
  up while you speak, and each sentence is committed about a second after you stop.
- **Live translation**: every committed sentence is translated with DeepL and saved next to the
  original.
- **Share with a QR code**: listeners open a read-only live view on their phone and pick their own
  language, with no sign-up. A "speaking…" bubble shows while a sentence is on its way.
- **Listen instead of read**: tap *Listen live* and each new line is read aloud (ElevenLabs TTS).
- **Keep it**: sessions are saved per account, with history, rename/delete, re-translation into
  another language, and a `.txt` download. A signed-in listener can add a session to their own list.

<table>
  <tr>
    <td align="center"><img src="docs/media/owner.png" alt="Owner's live view with the QR code" width="420"><br><sub>Speaker: live transcript + QR code</sub></td>
    <td align="center"><img src="docs/media/viewer.png" alt="Listener's phone view" width="220"><br><sub>Listener: their language, on their phone</sub></td>
    <td align="center"><img src="docs/media/history.png" alt="A saved session's transcript" width="420"><br><sub>History: every session, re-translatable</sub></td>
  </tr>
</table>

## Technical highlights

- **Streaming, not uploading.** An `AudioWorklet` sends raw PCM over a WebSocket; FastAPI proxies it
  straight into ElevenLabs' realtime endpoint and relays partial/committed transcripts back. After
  testing on real devices, the end-of-sentence delay was cut from 1.5 s to 1 s and the database
  write was taken off the path to the screen.
  ([why realtime](docs/decisions.md#real-time-elevenlabs-realtime-streaming-stt-not-rest-batch-chunks),
  [latency work](docs/decisions.md#live-latency-shorter-vad-silence-save-off-the-critical-path-speaking-flag-kan-65))
- **Anonymous listeners never touch the database.** They're served from an in-memory room that the
  speaker's own connection fills. Fan-out goes through a queue with per-listener send timeouts, so
  a slow phone can't stall the speaker. Each line is translated once per *language*, not once per
  listener. ([design, D1–D6](docs/decisions.md#phase-5-qr-code-live-viewer-kan-50))
- **The database enforces who sees what.** Every query runs with the signed-in user's own JWT under
  Postgres Row Level Security, and the service-role key is never used. Listeners get a separate
  WebSocket endpoint with no code path to speaker actions. Guest access goes through a
  `SECURITY DEFINER` function that verifies the share token inside Postgres.
  ([auth](docs/decisions.md#auth-supabase-js-on-the-client-jwt-verification--rls-via-user-token-on-the-backend),
  [D6](docs/decisions.md#phase-5-qr-code-live-viewer-kan-50))
- **Paid APIs are called once per line and language.** Generated speech is cached per
  `(message, language)` in Supabase Storage, so listeners switching languages or replaying lines
  can't run up the ElevenLabs bill.
- **Tested, then verified on real phones.** The backend (`pytest`) and frontend (`vitest`) suites
  run in CI on every push. Testing on real devices found bugs the unit tests couldn't, and each fix
  is written up. ([what real devices changed](docs/decisions.md#phase-5-changes-after-real-device-testing-kan-50))
- **Every decision is written down.** [`docs/decisions.md`](docs/decisions.md) records why each
  piece was built the way it was, and what was rejected.

## Why

At my previous job I co-built a real-time simultaneous translation system for municipal front-desk services (Python on AWS ECS, React, WebSockets, ElevenLabs). I also started a solo project called Raptor on the same idea that never shipped.

Pédiluve is my local rebuild of that architecture: full control over the pipeline, cheap to run, and a base to experiment with the parts that were left pending (speaker diarization, streaming STT, contextual translation).

## Architecture

Sign-up/sign-in/sign-out talk to Supabase Auth directly from the browser (`supabase-js`) — the
backend never sees a password, only the JWT that comes back from it:

```
┌─────────────┐   email + password    ┌──────────────┐
│   Browser    │ ──────────────────►  │ Supabase Auth │
│ (supabase-js)│ ◄──────────────────  │               │
└─────────────┘    session + JWT      └──────────────┘
```

A session itself is created up front over the REST API, not implicitly by the WebSocket — the
home page's "New session" modal names it, then opens its live view, which joins that same session
over the WebSocket rather than creating a new one:

```
┌──────────┐  POST /api/sessions  ┌──────────┐
│  Browser │ ────────────────────►│ FastAPI  │──► Supabase (sessions row created)
│  (home)  │ ◄────────────────────│  (REST)  │
└──────────┘   {id, title, ...}   └──────────┘
     │
     │ navigate to /sessions/:id/live
     ▼
```

Once on the live view, that JWT rides along on every WebSocket message, the connection joins the
session that was just created (or an existing one, on a pause/resume), and the audio itself
streams continuously rather than in fixed-size chunks:

```
┌─────────────────────┐  authenticate, join_session   ┌────────────┐                    ┌───────────────┐
│   Browser (React)   │───────► raw PCM + JWT ───────►│  FastAPI   │─── realtime WS ───►│  ElevenLabs   │
│ mic -> AudioWorklet │◄── session_joined, partial/ ───│  (Python)  │◄ partial/committed │  Scribe (RT)  │
└─────────────────────┘        committed transcripts   └────────────┘                    └───────────────┘
```

FastAPI then calls DeepL (REST) to translate each committed transcript, and Supabase (Postgres,
via that same user's JWT so Row Level Security applies) to persist it - both described below.

**Flow, once a session is joined:**
1. Browser captures mic audio with the Web Audio API + an `AudioWorklet`, streaming raw PCM continuously over WebSocket (no `MediaRecorder`/WebM — ElevenLabs' realtime endpoint needs uncompressed audio, so there's no container to convert)
2. Backend proxies that stream straight through to ElevenLabs' realtime STT WebSocket and relays `partial_transcript`/`committed_transcript` events back as they arrive
3. On each committed transcript, backend calls DeepL for translation
4. Backend pushes `{original_text, translated_text}` back over the same WebSocket
5. Backend persists the message to Supabase, scoped to the signed-in user and the joined session — Row Level Security, not application code, is what stops one user from ever reading another's rows
6. Browser renders both texts side by side, live

Recording can be paused and resumed any number of times within the same session (pausing doesn't
end it — only leaving the live view does); the session's full transcript stays available afterward
at its own read-only URL, from the sessions list on the home page.

**Sharing a live session (QR code):** the live view shows a QR code / link anyone can open at
`/view/:shareToken` — no account needed — to watch that session's transcript translate live, in
their own chosen language, on their own device. It's served by a second, anonymous WebSocket
endpoint (`/ws/view`) that never talks to Postgres directly: everything a viewer sees comes from an
in-memory room the owner's own connection populates as it commits and translates each line, so a
slow or malicious viewer connection can never affect the owner's own session. A signed-in viewer can
add the session to their own account ("Add to my sessions") to keep read-only access after the live
session ends. The viewer page is built for phones: it shows only the translation, can download it as
a text file, and has a **Listen live** mode that reads each new line aloud as it arrives. See `docs/decisions.md`'s "Phase 5: QR code live viewer" entry for the full
architecture.

## Stack

| Layer | Tech | Why |
|---|---|---|
| Frontend | React + Vite + TypeScript | Fast dev loop, familiar |
| Backend | Python + FastAPI | Async WebSocket support, same language as the original |
| STT | ElevenLabs Scribe (realtime) | Same provider as the original system, true streaming |
| Translation | DeepL API (Free tier) | 500k chars/month free, low latency |
| Auth | Supabase Auth (email + password) | No custom auth endpoints to build or secure |
| Routing | React Router | `/login` + per-session URLs, survives a reload |
| Styling | Tailwind CSS | Design tokens (colors, type scale) instead of hand-rolled CSS per component |
| TTS | ElevenLabs | On-demand playback, owner and QR viewers alike, cached per (message, language) |
| Sharing | `qrcode` (frontend) | Plain SVG/data-URL QR code for a session's read-only live view link |
| Persistence | Supabase (PostgreSQL) | Free tier, hosted, Row Level Security scopes data per user |

Everything runs on `localhost`. No deployment in v1: for a demo outside your network, a temporary
tunnel exposes it only while the demo runs (see [Public demo](#public-demo-through-a-temporary-tunnel-optional)).

## Roadmap

- [x] **Phase 0 — Setup**: repo structure, WebSocket echo, Supabase tables
- [x] **Phase 1 — Audio streaming**: mic → realtime STT → text on screen, persisted to Supabase
- [x] **Phase 2 — Translation**: target language selector, DeepL, side-by-side view
- [x] **Phase 3 — Accounts**: Supabase Auth (email + password), React Router (`/login` + a guarded app), sessions scoped to the signed-in user via Row Level Security
- [x] **Phase 4 — Session-first flow**: name and create a session explicitly (home page → "New session"), its live view joins that session over the WebSocket and can be paused/resumed without ending it, a past session's full transcript is a read-only page, re-translate it to another language on demand, rename/delete from the home list
- [x] **Phase 4.5 — Visual design**: Tailwind CSS with a small design-token system (colors, type scale), every page/component migrated off hand-written CSS, a redesigned paired-card transcript view
- [x] **Phase 5 — QR code live viewer + TTS**: a QR code / share link gives anyone a read-only live view of a session, translating live into their own language, no account needed; a signed-in viewer can add it to their own sessions; play a translated line back, generated once and cached in Supabase Storage, for the owner and viewers alike
- [x] **After Phase 5 — Real-device polish**: lower live latency (1 s end-of-sentence, database write off the path to the screen), a "speaking…" indicator for listeners, a one-command public demo through a temporary tunnel
- [ ] **Phase 6 — Spike** *(parked)*: speaker labels, only if a real multi-mic use case shows up; further voice-activity-detection tuning

## Running locally

### Supabase setup (one-time)

1. Create a project at [supabase.com](https://supabase.com) (or use an existing one).
2. **Authentication → Providers → Email**: make sure it's enabled.
3. **Authentication → Providers → Email → "Confirm email"**: turn this **off** for local dev (recommended) — with it on, registering returns no session until the user clicks a confirmation link, which needs an email template and a working "from" address neither of which this project sets up. Leave it on only if you specifically want to test that flow.
4. **SQL Editor → New query**: run, in order, `supabase/migrations/001_initial.sql`, `003_auth_and_rls.sql`, `004_nullable_target_language.sql`, `005_share_token.sql`, `006_message_audio.sql`, `007_message_audio_storage_bucket.sql`, then `008_session_guests.sql` (`002_disable_rls.sql` is superseded by 003 and only kept as history — skip it). This creates the schema, adds `sessions.user_id`, turns on Row Level Security with owner-only policies, (004) makes `sessions.target_language` nullable and adds a `unique(session_id, sequence)` constraint on `messages`, and (005–008) add the QR live viewer's `share_token`, the `message_audio` TTS cache table and its Storage bucket, and the `session_guests` table + `add_session_guest` RPC for "add to my sessions" (see `docs/decisions.md`'s Phase 5 entry).
5. **Project Settings → API**: copy the Project URL and the `anon` `public` key (never the `service_role` key — it bypasses Row Level Security entirely) for the `.env` files below.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # fill in your keys (ElevenLabs, DeepL, Supabase URL + anon key)
python -m pytest          # optional: backend test suite
uvicorn main:app --reload --port 8000 --timeout-graceful-shutdown 3
```

The browser never calls the backend directly: the Vite dev server proxies `/api` and `/ws` to it
(`frontend/vite.config.ts`), so uvicorn only has to listen on `localhost`, and phones on the LAN or
through a tunnel need nothing from it. uvicorn doesn't reload `.env` on `--reload`: restart it
after editing that file.

ElevenLabs: the API key needs both the Speech to Text and Text to Speech permissions, and on the
free plan `ELEVENLABS_VOICE_ID` must be one of the default voices (Voice Library voices return 402
through the API).

`--timeout-graceful-shutdown 3` caps how long Ctrl+C waits for open connections. Without it, on
Windows (Python 3.12, asyncio's default event loop) uvicorn can hang forever at "Shutting down"
while a viewer's `/ws/view` socket is still open: it waits in `asyncio.Server.wait_closed()`,
which a second Ctrl+C doesn't interrupt. With the flag it gives up after 3 seconds and exits.

### Frontend

```bash
cd frontend
npm install
cp ../.env.example .env   # only the VITE_ vars in it are read here
npm run dev   # http://localhost:5173
npm test      # optional: frontend test suite
```

For the QR live viewer on your Wi-Fi, set `VITE_SHARE_BASE_URL` in `frontend/.env` to your
machine's LAN origin (e.g. `http://192.168.1.42:5173`) and keep using `http://localhost:5173`
yourself. The browser only allows mic capture on `localhost` or https, so the owner can't record
from the LAN address, and a QR code built from `localhost` would point the phone at itself.

Open `http://localhost:5173`, register an account (redirects to `/login` automatically until you
do), click **New session** on the home page and give it a name, then start recording on its live
view. Pause and resume as needed; **End session** returns you to the home page, where the session
now appears in the list — click it to revisit its full transcript, or use the row's Rename/Delete
actions.

### Public demo through a temporary tunnel (optional)

To let someone outside your network follow a session (e.g. on mobile data), expose the frontend
through a [Cloudflare Quick Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/)
while the demo runs. This is not a deployment: nothing leaves your machine, and the URL dies with
the command.

1. Install `cloudflared` once (Windows: `winget install --id Cloudflare.cloudflared`).
2. Run the backend and frontend as above, then in a third terminal:
   `cloudflared tunnel --url http://localhost:5173`
3. Open the `https://<random>.trycloudflare.com` URL it prints and sign in there. It's https, so
   the mic works from any device, and the QR code carries that URL automatically.

While the tunnel is up, anyone with the URL can reach the app, and sign-up is open while ElevenLabs
and DeepL are paid per use. Before a demo, turn off Supabase's **"Allow new users to sign
up"** setting (under Authentication). Stop the tunnel (Ctrl+C) as soon as the demo is over.

## Decisions log

See [`docs/decisions.md`](docs/decisions.md) for why each tech was chosen over alternatives.

## Author

Manel Gonzalez Rico — [LinkedIn](https://linkedin.com/in/manel-gonzalez-rico) · [GitHub](https://github.com/Manel-Gonzalez)
