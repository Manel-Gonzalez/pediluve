-- Pédiluve — Storage bucket for cached TTS audio (KAN-30)
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New query)
--
-- Object paths are {owner_id}/{session_id}/{message_id}.{language}.mp3
-- (services/storage.py) - deterministic and owner-prefixed, so ordinary
-- owner-scoped RLS on storage.objects is enough (no service-role key, same
-- invariant as everywhere else in this project). A viewer never talks to
-- Storage directly; the backend generates a short-lived signed URL using
-- the live owner connection's own JWT and sends only that over /ws/view.

insert into storage.buckets (id, name, public)
values ('message-audio', 'message-audio', false)
on conflict (id) do nothing;

create policy "message-audio: owner select" on storage.objects for select
  using (bucket_id = 'message-audio' and auth.uid()::text = (storage.foldername(name))[1]);

create policy "message-audio: owner insert" on storage.objects for insert
  with check (bucket_id = 'message-audio' and auth.uid()::text = (storage.foldername(name))[1]);

create policy "message-audio: owner delete" on storage.objects for delete
  using (bucket_id = 'message-audio' and auth.uid()::text = (storage.foldername(name))[1]);
