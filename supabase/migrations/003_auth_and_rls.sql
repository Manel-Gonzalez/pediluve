-- Pédiluve — user accounts + Row Level Security (Phase 3 / KAN-13)
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New query)
--
-- Supersedes 002_disable_rls.sql: this is the "if this ever goes multi-user"
-- moment 001_initial.sql's RLS comment anticipated. From here on, RLS is
-- enforced by Postgres via auth.uid() policies, not left off - the backend
-- attaches each signed-in user's JWT to every Supabase query (see
-- services/auth.py, services/supabase.py) so auth.uid() resolves inside them.

alter table sessions
  add column user_id uuid references auth.users(id) on delete cascade;

-- Phase 0-2 test rows have no owner and no value: delete them (cascades to
-- messages via the existing FK), then make ownership mandatory.
delete from sessions where user_id is null;
alter table sessions alter column user_id set not null;
alter table sessions alter column user_id set default auth.uid();

-- Exactly the index Phase 4's session-list query needs (user_id, newest
-- first), so it goes in now rather than as an afterthought later.
create index if not exists sessions_user_created_idx on sessions(user_id, created_at desc);

alter table sessions enable row level security;
alter table messages enable row level security;

create policy "sessions: owner select" on sessions for select using (user_id = auth.uid());
create policy "sessions: owner insert" on sessions for insert with check (user_id = auth.uid());
create policy "sessions: owner update" on sessions for update using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "sessions: owner delete" on sessions for delete using (user_id = auth.uid());

-- messages has no user_id of its own - ownership is via its session.
create policy "messages: via owned session" on messages for all
  using  (exists (select 1 from sessions s where s.id = messages.session_id and s.user_id = auth.uid()))
  with check (exists (select 1 from sessions s where s.id = messages.session_id and s.user_id = auth.uid()));
