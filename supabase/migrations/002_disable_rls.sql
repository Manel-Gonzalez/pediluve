-- Pédiluve — re-assert RLS off
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New query)
--
-- 001_initial.sql already disabled RLS on both tables, but Supabase's
-- dashboard security nag (the "Unrestricted table" warning) prompts you to
-- re-enable it with a starter read-only policy. That silently breaks
-- inserts/updates from the backend, which uses the anon/publishable key.
-- This app has no auth (CLAUDE.md: "single-user local app") - RLS with
-- proper policies only makes sense once that changes.

alter table sessions disable row level security;
alter table messages disable row level security;
