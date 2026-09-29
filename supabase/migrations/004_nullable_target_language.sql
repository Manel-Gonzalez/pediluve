-- Pédiluve — sessions.target_language becomes nullable (Phase 4 / KAN-22)
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New query)
--
-- docs/decisions.md's "Phase 2: sessions.target_language can hold a meaningless
-- placeholder" flagged this exact moment: create_session() used to write "en"
-- when no target language had ever been chosen, so sessions.target_language
-- could not be trusted to mean "this session has translations" - only
-- messages.translated_text being non-null actually means that. Dropping NOT
-- NULL lets create_session() write the true "never chosen" state instead of
-- a placeholder, resolving that ambiguity at the source rather than working
-- around it in every reader.
--
-- No backfill: dropping a NOT NULL constraint doesn't touch existing data,
-- and existing "en"-placeholder rows staying "en" is harmless - they still
-- correctly have no translated messages, per the same reasoning above.

alter table sessions alter column target_language drop not null;
