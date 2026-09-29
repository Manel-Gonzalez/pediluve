// Mirrors backend/models/sessions.py's SessionTitle: trim, then 1..120 chars.
// Shared by the create modal (KAN-37) and the rename row action (KAN-39) so
// both surfaces reject the exact same input the API would 422 on, instead of
// a round trip being the first place the user finds out.
export type SessionTitleValidation = { ok: true; title: string } | { ok: false; error: string }

const MAX_TITLE_LENGTH = 120

export function validateSessionTitle(raw: string): SessionTitleValidation {
  const title = raw.trim()
  if (title.length === 0) return { ok: false, error: 'Title is required' }
  if (title.length > MAX_TITLE_LENGTH) {
    return { ok: false, error: `Title must be ${MAX_TITLE_LENGTH} characters or fewer` }
  }
  return { ok: true, title }
}
