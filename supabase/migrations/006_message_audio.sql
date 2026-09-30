-- Pédiluve — cached TTS audio (Phase 5 / KAN-50's Milestone B, KAN-28)
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New query)
--
-- Keyed by (message_id, language) rather than a single audio_path column on
-- messages: a session's own viewers (KAN-50) each pick their own display
-- language independently of messages.target_language, so the same message
-- can need audio cached in several languages at once. Caching only the
-- session's canonical language would let anonymous QR viewers trigger
-- unbounded ElevenLabs spend (lines x languages x viewers) - see
-- docs/decisions.md's D5 once KAN-64 writes it up.
--
-- storage_path is the Supabase Storage object key, not the audio itself -
-- {owner_id}/{session_id}/{message_id}.{language}.mp3 (services/storage.py,
-- KAN-30), deterministic so the existing prefix-delete-on-session-delete
-- logic (KAN-32) stays a single-level Storage `list`.

create table if not exists message_audio (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references messages(id) on delete cascade,
  language text not null,
  storage_path text not null,
  created_at timestamptz not null default now(),
  unique (message_id, language)
);

alter table message_audio enable row level security;

-- Written and read only by the backend acting as the session's owner (the
-- live owner connection's own JWT, per D5 - a viewer never queries this
-- table directly, only ever receives a signed Storage URL over /ws/view).
create policy "message_audio: via owned session" on message_audio for all
  using (
    exists (
      select 1 from messages m
      join sessions s on s.id = m.session_id
      where m.id = message_audio.message_id and s.user_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1 from messages m
      join sessions s on s.id = m.session_id
      where m.id = message_audio.message_id and s.user_id = auth.uid()
    )
  );
