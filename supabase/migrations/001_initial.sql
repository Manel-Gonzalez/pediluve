-- Pédiluve — initial schema
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New query)

-- A session is one recording run: user clicks "start", speaks, clicks "stop".
create table if not exists sessions (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  ended_at timestamptz,
  source_language text,                -- detected or chosen, e.g. 'es', 'ca', 'en'
  target_language text not null,       -- what the user asked to translate to
  title text                           -- optional, user can rename later
);

-- A message is one transcribed + translated chunk within a session.
create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references sessions(id) on delete cascade,
  created_at timestamptz not null default now(),
  sequence int not null,               -- order within the session, 0-based
  original_text text not null,
  translated_text text,                -- null until Phase 2 fills it
  target_language text,                -- copied from session, allows re-translation later
  speaker text,                        -- null for now, Phase 5 will fill it
  audio_duration_ms int                -- how long the chunk was
);

create index if not exists messages_session_idx on messages(session_id, sequence);

-- Row Level Security: off for now (single-user local app, Phase 0).
-- Turn on and add policies if this ever goes multi-user.
alter table sessions disable row level security;
alter table messages disable row level security;
