import type { Session } from '@supabase/supabase-js'
import type {
  SessionDetail,
  SessionListResponse,
  SessionSummary,
  TranslateResponse,
} from './types'

// Backend's dev port (uvicorn). Not configurable separately from
// VITE_WS_URL/VITE_API_URL - set one of those instead if it ever needs to
// differ from the frontend's own host.
const BACKEND_PORT = '8000'

type LocationLike = { hostname: string; protocol: string }

// A guest opening the QR/share link on their own phone loads the frontend
// from this machine's LAN IP, not "localhost" - "localhost" on their phone
// means their phone. Deriving the backend host from the page's own location
// (falling back to it) means the same build works for both the owner
// (https://localhost:5173) and a LAN guest (http://192.168.x.x:5173)
// without an env var per device. VITE_WS_URL/VITE_API_URL still win when
// set, for anything this heuristic can't handle (a reverse proxy, a
// different backend host entirely).
//
// `location` is injectable (rather than always reading `window.location`
// directly) so getApiUrl/getWebSocketUrl stay plain, unit-testable
// functions - no jsdom needed, matching this project's "don't force tests
// onto browser APIs" convention (see CLAUDE.md).
function currentLocation(): LocationLike | undefined {
  return typeof window !== 'undefined' ? window.location : undefined
}

export function getWebSocketUrl(location: LocationLike | undefined = currentLocation()): string {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL
  const protocol = location?.protocol === 'https:' ? 'wss' : 'ws'
  const host = location?.hostname || 'localhost'
  return `${protocol}://${host}:${BACKEND_PORT}/ws`
}

// The anonymous viewer counterpart to getWebSocketUrl (backend's /ws/view,
// KAN-55) - derived from VITE_WS_URL by swapping its path when that's set,
// so a deployment only needs to configure the one env var for both.
export function getViewerWebSocketUrl(
  location: LocationLike | undefined = currentLocation(),
): string {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL.replace(/\/ws$/, '/ws/view')
  const protocol = location?.protocol === 'https:' ? 'wss' : 'ws'
  const host = location?.hostname || 'localhost'
  return `${protocol}://${host}:${BACKEND_PORT}/ws/view`
}

export function getChunkDurationMs(): number {
  return Number(import.meta.env.VITE_CHUNK_DURATION_MS) || 250
}

export function getApiUrl(location: LocationLike | undefined = currentLocation()): string {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL
  const protocol = location?.protocol === 'https:' ? 'https' : 'http'
  const host = location?.hostname || 'localhost'
  return `${protocol}://${host}:${BACKEND_PORT}`
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

// "Add to my sessions" (KAN-62): a signed-in guest adds a live/past session
// to their own account via its share link, without ever seeing its
// share_token beyond what the URL already gave them.
export function addGuestSession(
  session: Session,
  shareToken: string,
  targetLanguage: string | null,
): Promise<SessionSummary> {
  return apiFetch('/api/shared/guest', session, {
    method: 'POST',
    body: JSON.stringify({ share_token: shareToken, target_language: targetLanguage }),
  })
}

export function removeGuestSession(session: Session, id: string): Promise<void> {
  return apiFetch(`/api/sessions/${id}/guest`, session, { method: 'DELETE' })
}
