---
name: plan-task
description: Plan and break down a feature or piece of work for Pédiluve into a well-specified Jira parent issue plus labeled, dependency-ordered subtasks in project KAN, then create them after the user approves. Use this whenever Manel wants to start a new phase, feature, or chunk of work, asks to "plan", "break down", "split up", "atomize", "spec out", "scope", or "create tickets/issues/subtasks" for something, wants help deciding what order to build things in, or pastes a rough idea or an existing KAN-issue key and wants it turned into actionable tasks. Reach for it even when the request is casual ("ok let's think about phase 3", "what should the translation work look like") — planning before coding is the project's default workflow, not an optional extra.
---

# plan-task

Turn a rough description of work into a Jira parent issue with labeled, ordered subtasks,
the way KAN-4 (Phase 2) was split into KAN-5..KAN-8. The output of this skill is a set of
issues on the KAN board that someone (usually Claude in a later session) can pick up one at
a time and implement without re-deriving the plan.

The skill has five moves: pick the model, gather context, clarify, propose, create.
Everything before "create" is read-only; nothing is written to Jira until the user says go.

## 1. Pick the model for the planning work

Ask which model should do the actual planning before doing anything else. Manel wants this
choice every time rather than a baked-in default, because the right tier depends on how
ambiguous the task is, and only he knows that at the moment of asking.

Use `AskUserQuestion` (load it with ToolSearch if it is not already in context; fall back to
a plain-text question with the same four options if the tool is unavailable). Offer:

| Option | When it fits |
|---|---|
| **Haiku 4.5** | Trivial, well-defined, low-ambiguity work: rename something across the codebase, swap a palette, a small chore where the breakdown is obvious. |
| **Sonnet 5** | The default for a typical, moderately scoped feature. Pick this when unsure. |
| **Opus 5.5** | Complex or ambiguous work with many interacting parts, where getting the breakdown wrong costs real time. |
| **Fable 5.1** | Same tier as Opus: high-stakes or genuinely unclear scope. Use when the task needs the strongest reasoning available. |

Map the pick to the Agent tool's `model` parameter: `haiku`, `sonnet`, `opus`, `fable`.

The heavy reasoning then happens inside one `Agent` call with that `model` set (see step 4),
not by switching the session's model. This keeps the planning isolated to a single subagent
on the tier that fits, while the orchestration (questions, approval, Jira writes) stays in
the main session where the user can interject.

## 2. Gather input and context

Input is one or more of:

- a plain-English description of what to build (often rough and unstructured);
- an existing Jira issue key (e.g. `KAN-9`) to read and refine;
- both.

Read the repo before forming any opinion. A plan that ignores what already exists is worse
than no plan, because it will propose work that is already done or contradict a decision
that was made deliberately. At minimum:

- `CLAUDE.md`: stack, phase gates, testing philosophy, conventions, "Current status".
- `docs/decisions.md`: why things are the way they are, and which decisions are flagged
  "revisit" (a task that touches one of those should say so).
- The code and tests the task will touch. Currently that means `backend/routers/ws.py`,
  `backend/services/*.py`, `backend/models/messages.py`, `backend/tests/`,
  `frontend/src/hooks/`, `frontend/src/lib/types.ts`, `frontend/src/App.tsx`,
  `frontend/src/audio/`, and `supabase/migrations/`. Adjust as the repo grows.

If a Jira key is given, or the task might overlap with tickets already on the board, use
the Atlassian MCP tools (search issues by JQL, get an issue by key) to read them. The tool
names in this session are prefixed with a connector UUID that can change between
reconnects, so find them by capability with ToolSearch rather than assuming a fixed name.
A JQL like `project = KAN ORDER BY created DESC` is a cheap way to see what is already
planned and avoid duplicating it.

## 3. Ask the clarifying questions that actually matter

Before proposing a plan, ask the user about whatever is genuinely ambiguous in *this* task.
Not a fixed checklist; a short list (often one to three questions, sometimes zero) that
comes from having read the task and the code and noticing where a reasonable engineer could
go two different ways.

Why bother: a breakdown built on an unstated assumption gets implemented, reviewed, and
then partly thrown away when the assumption turns out wrong. One question up front is far
cheaper than that. But questions whose answer is already in the task description, in the
existing acceptance criteria, or in `CLAUDE.md` waste the user's attention and make the
skill feel like a form to fill in, so check those sources first.

Dimensions that are often worth checking, when they are actually unclear:

- **Scope boundary.** Where does this feature stop? "Language selector" could mean a
  dropdown of five languages or auto-detection plus a full DeepL language list.
- **Explicit out-of-scope.** Things the user is deliberately deferring that a naive plan
  would include (persistence, UI polish, a follow-up phase's concern).
- **Dependencies on unfinished work.** Does this rely on something not yet merged to `main`?
  Phase gates in `CLAUDE.md` say a phase does not start until the previous one is merged.
- **Contract changes.** Does the work change the WebSocket message format or the Supabase
  schema? `CLAUDE.md` says to ask before changing the message format, so a plan that does
  should surface it explicitly rather than bury it in a subtask.
- **Verification.** For anything browser-API-heavy, what does "works" look like when
  checked by hand? That becomes an acceptance criterion.

`AskUserQuestion` is a good fit when the question has a small set of discrete answers;
plain text is fine for open-ended ones. Batch the questions into one turn rather than
drip-feeding them.

## 4. Do the planning in a subagent on the chosen model

Spawn one `Agent` (subagent_type `general-purpose`, `model` from step 1,
`run_in_background: false` since the next step depends on its result). Give it everything
it needs to work without the conversation: the task text, the Jira key and fetched issue
content if any, the user's answers to the clarifying questions, the paths listed in step 2,
and a pointer to `references/issue-templates.md` in this skill's directory for the output
shape. Ask it to read the repo itself rather than paraphrasing the code for it.

Tell the subagent to return, in its final message, a proposal with these parts:

1. **Parent issue** in the What / Why / Acceptance criteria / Out of scope structure
   (plus a "Message contract (draft)" or "Schema change (draft)" section when the task
   changes a wire format or table, since that is where the real design decisions live).
2. **Subtasks**, each with a title, a label, its own What and Acceptance criteria, and
   explicit "Depends on" notes naming the subtask it waits on and why.
3. **Suggested additions**: things a careful colleague would flag that the user did not
   mention. Be specific to this task, not generic. Examples of the kind of thing to look
   for: a migration the persistence change implies, an error path the happy-path spec
   leaves undefined (what does the client see when DeepL times out?), a test-coverage gap
   in existing code the change will lean on, a `docs/decisions.md` entry the choice
   warrants, a cleanup the change makes possible. Present these as separate candidates the
   user can accept or drop, not silently folded into the plan.
4. **Ordering with rationale.** Say why this order and not another: what unblocks the most
   other work, what reduces risk earliest (usually: nail the contract and the backend
   service with tests first, then the UI that consumes it), what can be done in parallel.
   A numbered list without reasons is not a prioritisation.
5. **Open questions or assumptions** it had to make, so the main session can surface them.

If the user's answers in the approval step change something material, continue the same
subagent with `SendMessage` so it revises with its context intact instead of starting over.

### Sizing and labels

- A subtask should be implementable in one focused session and land as one to three
  conventional commits. If a subtask needs its own sub-breakdown, it is a parent, not a
  subtask; if it is a single line change, fold it into a neighbour.
- Each subtask must be independently verifiable: its acceptance criteria are checkable
  without the rest of the parent being done, given its dependencies are.
- Labels are lowercase single words, reusing what is already on the board (`frontend`,
  `backend`). Add others only when the work genuinely is not one of those, e.g. `db` for a
  migration-only task, `docs`, `infra`, `test`. Infer the taxonomy from the task rather
  than forcing every plan into a frontend/backend split. Labels, not Components: the
  Atlassian connector cannot create Components, and labels are created on first use.

### Conventions the plan should carry

The subtasks are executed by a Claude session reading `CLAUDE.md`, so the plan should be
consistent with it rather than restate it. Specifically:

- Backend services and pure frontend logic follow spec, then test, then implementation.
  A backend subtask's acceptance criteria should name the test file and what it covers
  (`backend/tests/test_deepl_service.py: translate() returns ..., raises on ...`), mocking
  external clients rather than calling ElevenLabs or DeepL for real.
- Browser-API-heavy work (`AudioWorklet`, `MediaStream`, `AudioContext`) is verified by
  hand in a real browser; say what to check rather than demanding a test.
- Conventional commits, one logical change per commit; one branch per Jira card
  (`feature/<KAN-N>` for a phase's parent Story, `fix/<KAN-N>`, `chore/<KAN-N>` —
  see CLAUDE.md), subtasks are commits on the parent's branch, not their own branches.
- Every new request/response shape gets a Pydantic model and a matching TypeScript type.
- New dependencies, folder structure changes, and WebSocket message format changes need a
  yes from the user; a subtask that introduces one should say so in its What.

## 5. Show the proposal, get a go-ahead, then create the issues

Present the subagent's proposal in chat: parent, subtasks with labels and dependencies,
the suggested additions as a separate list, and the ordering rationale. Ask the user to
accept, edit, or drop pieces. Do not write to the board until they say go; it is their
board, and cleaning up wrong issues in Jira is slower than editing a message.

Once approved, using the Atlassian MCP tools (create issue, edit issue; find by capability):

1. Create the parent as a **Story** in project `KAN` (or update the existing issue if one
   was given), with the full description from the template.
2. Create each subtask as issue type **Subtask** with the parent set, the label(s) set, and
   its own description. Create them in dependency order so the "Depends on KAN-n" notes can
   reference real keys; fill those in after each key comes back.
3. Report the created keys and titles back in chat, in order, with a one-line "start with
   KAN-n" recommendation.

Reference `references/issue-templates.md` for the exact description layout and a worked
example. The layout matters because later sessions parse these descriptions to know when a
subtask is done; keep the headings consistent.

If the connector refuses a write (permissions, rate limit, an unexpected required field),
say what failed and what was created so far. Do not retry blindly and do not silently fall
back to creating a different issue type.

## What this skill does not do

- It does not implement anything. The next step after this skill is a fresh session on
  one subtask.
- It does not switch the session's model or modify `CLAUDE.md`. If the plan changes the
  phase status, mention that `CLAUDE.md`'s "Current status" should be updated when the
  phase branch is created, but leave that to the implementation session.
- It does not transition or close issues.
