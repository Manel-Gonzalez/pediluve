-- Pédiluve — guests: "add to my sessions" (KAN-50's Milestone C, KAN-59)
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New query)
--
-- The deliberate, narrow exception to CLAUDE.md's "don't add multi-tenant/
-- org complexity" rule: one fixed read-only relationship (a guest can read
-- a session and its messages, nothing else), no roles table, no admin
-- features. Rename/delete/target_language stay owner-only, enforced the
-- same way as everywhere else in this project: RLS, not an application
-- check.
--
-- Insertion goes through the add_session_guest() RPC below rather than a
-- plain INSERT policy on session_guests: every browser already holds the
-- anon key plus the signed-in user's own JWT and can call PostgREST
-- directly, so a policy shaped like `user_id = auth.uid()` would let *any*
-- signed-in user add themselves as a guest to *any* session id - the check
-- has to also verify the caller actually holds that session's share_token,
-- which only the function (not a declarative RLS policy) can do.

create table if not exists session_guests (
  session_id uuid not null references sessions(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  -- The guest's own preferred display language for this session, distinct
  -- from sessions.target_language (the owner's) - same idea as a /ws/view
  -- viewer picking their own language independently of the session's own.
  target_language text,
  added_at timestamptz not null default now(),
  primary key (session_id, user_id)
);

alter table session_guests enable row level security;

create policy "session_guests: guest select own" on session_guests for select
  using (user_id = auth.uid());

-- "Remove from my sessions" (KAN-60's DELETE /api/sessions/{id}/guest) -
-- a guest may only ever remove themselves, never another guest, and never
-- touches other tables' rows (the FK cascade is one-directional: deleting
-- the session deletes guest rows, not the other way around).
create policy "session_guests: guest delete own" on session_guests for delete
  using (user_id = auth.uid());

-- Additive to the existing owner-only policies (003_auth_and_rls.sql) -
-- Postgres OR's multiple permissive policies for the same command, so this
-- only ever *widens* who can SELECT; insert/update/delete on sessions and
-- messages stay exactly as owner-only as before.
create policy "sessions: guest select" on sessions for select
  using (
    exists (
      select 1 from session_guests g where g.session_id = sessions.id and g.user_id = auth.uid()
    )
  );

create policy "messages: guest select via owned session" on messages for select
  using (
    exists (
      select 1 from session_guests g
      where g.session_id = messages.session_id and g.user_id = auth.uid()
    )
  );

-- SECURITY DEFINER so it can look up the session by share_token (a guest's
-- own RLS wouldn't yet let them see that row - they're not a guest until
-- this function makes them one) while still forcing user_id = auth.uid()
-- itself, never trusting a caller-supplied id. search_path = '' plus fully
-- schema-qualified names throughout close off the classic search-path
-- hijack; execute is revoked from anon/public and granted only to
-- authenticated, so only a signed-in user can ever call it.
create or replace function add_session_guest(share_token uuid, target_language text default null)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  target_session_id uuid;
begin
  select id into target_session_id
  from public.sessions
  where sessions.share_token = add_session_guest.share_token;

  if target_session_id is null then
    raise exception 'Session not found';
  end if;

  insert into public.session_guests (session_id, user_id, target_language)
  values (target_session_id, auth.uid(), add_session_guest.target_language)
  on conflict (session_id, user_id) do update set target_language = excluded.target_language;
end;
$$;

revoke all on function add_session_guest(uuid, text) from public;
grant execute on function add_session_guest(uuid, text) to authenticated;
