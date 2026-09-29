import type { SessionSummary } from './types'

// "Untitled - <date>" for a session with no title. Shouldn't happen once
// KAN-37's create modal requires one, but keeps the list robust against
// older or malformed rows rather than rendering a blank row.
export function formatSessionTitle(session: SessionSummary): string {
  if (session.title) return session.title
  return `Untitled - ${new Date(session.created_at).toLocaleDateString()}`
}

// "Load more" appends a page rather than replacing the list - the rows
// already on screen must stay while a further page loads.
export function appendSessions(
  existing: SessionSummary[],
  loaded: SessionSummary[],
): SessionSummary[] {
  return [...existing, ...loaded]
}

// Rename-in-place (KAN-39): a successful PATCH updates just the one row's
// title, not a refetch of the whole list.
export function renameSessionInList(
  sessions: SessionSummary[],
  id: string,
  title: string,
): SessionSummary[] {
  return sessions.map((s) => (s.id === id ? { ...s, title } : s))
}

// Shared by both a successful DELETE and a 404 on either rename or delete
// (the row was removed elsewhere, e.g. another tab) - either way the row no
// longer belongs in the list, and a refetch isn't needed to know that.
export function removeSessionFromList(sessions: SessionSummary[], id: string): SessionSummary[] {
  return sessions.filter((s) => s.id !== id)
}
