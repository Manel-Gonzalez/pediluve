-- KAN-51: sessions.share_token — capability token for the QR live viewer (KAN-50).
--
-- A dedicated column rather than reusing sessions.id: id already appears in
-- owner-facing URLs (/sessions/:id, /sessions/:id/live), and a capability
-- link needs to be revocable without changing the session's real identity.
-- Revoking access later is just `update sessions set share_token =
-- gen_random_uuid() where id = ...` — every previously-printed QR code /
-- shared link stops working, the session itself is untouched.
--
-- Anonymous viewers (routers/viewer_ws.py, /ws/view) never query Postgres
-- directly - the token is only ever looked up against the in-memory
-- LiveRoom registry that owner connections populate (see docs/decisions.md).
-- RLS on this column therefore doesn't need to grant anon anything; it's
-- listed here only so owners can read their own session's token back over
-- the existing owner-scoped REST/WS paths.

alter table sessions
  add column share_token uuid not null default gen_random_uuid();

alter table sessions
  add constraint sessions_share_token_unique unique (share_token);
