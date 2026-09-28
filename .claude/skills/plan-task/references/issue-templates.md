# Issue templates and a worked example

The parent/subtask layout established with KAN-4 (Phase 2) and its subtasks KAN-5..KAN-8.
Keep the headings verbatim so later sessions can rely on them.

## Parent issue (Story)

Title: short, phase-prefixed when it is a phase: `Phase 2: language selector + DeepL translation + two-column view`.
For a non-phase feature: a noun phrase naming the outcome, e.g. `Sessions list page`.

Description (Markdown):

```markdown
## What
One or two paragraphs. What the user can do once this is done that they cannot do now.
Name the concrete surfaces touched (endpoint, hook, table, component).

## Why
Why now, and why this shape. Link to the phase gate in CLAUDE.md or the decision in
docs/decisions.md when one applies. Two to four sentences.

## Acceptance criteria
- [ ] Observable, checkable statements. Each one is something a reviewer can confirm.
- [ ] Include the test expectation for backend/pure logic ("pytest passes with N new tests in ...").
- [ ] Include the manual check for browser-heavy parts ("speaking in ES with target EN shows ...").
- [ ] Include persistence expectations when data is saved ("row in `messages` has `translation` and `target_lang`").

## Out of scope
- Things deliberately deferred, each with where they go instead (a later phase, a follow-up issue).

## Message contract (draft)
Only when the work changes a wire format or schema. Show the new/changed JSON shapes
client -> server and server -> client, and the Pydantic/TS types that will mirror them.
Mark it "(draft)" because the implementing session may adjust it, with a note in the PR.
```

Optional extra sections when they earn their place: `## Schema change (draft)`,
`## Risks`, `## References` (API docs consulted).

## Subtask

Title: imperative, specific, under ~70 chars: `Add DeepL translation service with tests`,
`Add target-language selector to the UI`.

Label(s): lowercase, one word each. Existing: `frontend`, `backend`. Add `db`, `docs`,
`test`, `infra` only when the work is genuinely not frontend or backend code.

Description (Markdown):

```markdown
## What
Two to five sentences. Files to create or change, by path. The approach if it is not obvious.

## Acceptance criteria
- [ ] Checkable statements scoped to this subtask only.
- [ ] For backend services / pure logic: the test file and what it asserts, written first.
- [ ] For browser-heavy work: what to verify by hand and how.

## Depends on
KAN-n (why: e.g. "needs the `target_lang` field in the client->server contract from KAN-n").
Write "Nothing" when it can start immediately; that makes the parallelisable work obvious.
```

## Worked example (Phase 2, condensed)

Illustrative of the shape and the level of detail, not a verbatim copy of the board.

**Parent, Story, `Phase 2: language selector + DeepL translation + two-column view`**

- What: user picks a target language; each committed transcript is translated by DeepL
  on the backend and both texts are shown side by side; translation saved with the original.
- Why: Phase 2 gate in CLAUDE.md; DeepL chosen in decisions.md for latency and free tier.
- Acceptance criteria: selector visible before recording starts; committed lines render
  original + translation; partials render original only; translation persisted;
  `pytest` and `vitest` green with new tests for the DeepL service and message parsing.
- Out of scope: re-translating past sessions (Phase 3), TTS (Phase 4), translating partials.
- Message contract (draft): client `start` gains `target_lang`; server `committed_transcript`
  gains `translation` and `target_lang`.

**Subtasks, in dependency order**

1. `backend` — Extend WS message models for `target_lang` and `translation`.
   Depends on: nothing. Unblocks everything else, so it goes first.
2. `backend` — Add DeepL service (`services/deepl.py`) with tests, mocked client.
   Depends on: nothing (can run in parallel with 1). Test first: translate returns text,
   propagates API errors as our error type, respects source-language auto-detect.
3. `backend` — Call DeepL on committed transcripts in `routers/ws.py`, persist translation.
   Depends on: 1 and 2. `messages.translated_text`/`target_language` already exist in the
   schema (currently always NULL) - no migration needed, just start writing real values.
4. `frontend` — Language selector + two-column view, TS types updated to match 1.
   Depends on: 1 (contract). Can be built against a stubbed server message before 3 lands.
   Verified by hand in the browser; the pure parsing helper gets a vitest.

**Suggested additions surfaced separately**

- Error path: what the client shows when DeepL fails (send `{type: "error"}` and still show
  the original?). Worth a line in the parent's acceptance criteria.
- DeepL Free quota: log character usage per session so hitting 500k/month is visible.
- decisions.md: note whether translation happens on `committed_transcript` only and why.
