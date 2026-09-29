import type { Session } from '@supabase/supabase-js'
import type {
  SessionDetail,
  SessionListResponse,
  SessionSummary,
  TranslateResponse,
} from './types'

export function getWebSocketUrl(): string {
  return import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws'
}

export function getChunkDurationMs(): number {
  return Number(import.meta.env.VITE_CHUNK_DURATION_MS) || 250
}

export function getApiUrl(): string {
  return import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
}

// Carries the HTTP status alongside FastAPI's `detail` message, so callers
// can branch on status (e.g. 401 -> send the user to /login) without
// re-parsing the response themselves.
export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function apiFetch<T>(path: string, session: Session, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${getApiUrl()}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...init.headers,
      Authorization: `Bearer ${session.access_token}`,
    },
  })

  if (!response.ok) {
    // FastAPI's default error body is {"detail": "..."} - fall back to the
    // status text if the body isn't JSON (e.g. a proxy/network error page).
    const body: unknown = await response.json().catch(() => null)
    const detail =
      body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string'
        ? body.detail
        : response.statusText
    throw new ApiError(response.status, detail)
  }

  // DELETE returns 204 with no body - nothing to parse.
  if (response.status === 204) return undefined as T

  return response.json() as Promise<T>
}

// Exported for testing: builds the query string for GET /api/sessions,
// omitting a param entirely rather than sending an empty/undefined value.
export function buildSessionListQuery(options: { limit?: number; offset?: number } = {}): string {
  const params = new URLSearchParams()
  if (options.limit !== undefined) params.set('limit', String(options.limit))
  if (options.offset !== undefined) params.set('offset', String(options.offset))
  const query = params.toString()
  return query ? `?${query}` : ''
}

export function createSession(session: Session, title: string): Promise<SessionSummary> {
  return apiFetch('/api/sessions', session, {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
}

export function listSessions(
  session: Session,
  options: { limit?: number; offset?: number } = {},
): Promise<SessionListResponse> {
  return apiFetch(`/api/sessions${buildSessionListQuery(options)}`, session)
}

export function getSession(session: Session, id: string): Promise<SessionDetail> {
  return apiFetch(`/api/sessions/${id}`, session)
}

export function renameSession(
  session: Session,
  id: string,
  title: string,
): Promise<SessionSummary> {
  return apiFetch(`/api/sessions/${id}`, session, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  })
}

export function deleteSession(session: Session, id: string): Promise<void> {
  return apiFetch(`/api/sessions/${id}`, session, { method: 'DELETE' })
}

export function translateSession(
  session: Session,
  id: string,
  targetLanguage: string,
): Promise<TranslateResponse> {
  return apiFetch(`/api/sessions/${id}/translate`, session, {
    method: 'POST',
    body: JSON.stringify({ target_language: targetLanguage }),
  })
}
