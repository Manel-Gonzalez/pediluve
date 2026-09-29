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
