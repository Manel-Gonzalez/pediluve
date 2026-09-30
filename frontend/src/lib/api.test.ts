import type { Session } from '@supabase/supabase-js'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  buildSessionListQuery,
  createSession,
  deleteSession,
  downloadTranscript,
  getApiUrl,
  getSession,
  getViewerWebSocketUrl,
  getWebSocketUrl,
  listSessions,
} from './api'


const SESSION = { access_token: 'tok-123' } as Session

afterEach(() => {
  vi.unstubAllGlobals()
})

function stubFetch(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('buildSessionListQuery', () => {
  it('returns an empty string when no options are given', () => {
    expect(buildSessionListQuery()).toBe('')
  })

  it('omits a param that was not given', () => {
    expect(buildSessionListQuery({ limit: 20 })).toBe('?limit=20')
  })

  it('includes both params when both are given', () => {
    expect(buildSessionListQuery({ limit: 20, offset: 40 })).toBe('?limit=20&offset=40')
  })
})

describe('apiFetch (via the typed wrappers)', () => {
  it('sends the Bearer token from the session', async () => {
    const fetchMock = stubFetch(new Response(JSON.stringify({ items: [], has_more: false }), { status: 200 }))

    await listSessions(SESSION)

    const [, init] = fetchMock.mock.calls[0]
    const headers = new Headers(init.headers)
    expect(headers.get('Authorization')).toBe('Bearer tok-123')
  })

  it('sends a JSON content-type and body for a request with a body', async () => {
    const fetchMock = stubFetch(
      new Response(
        JSON.stringify({
          id: 's1',
          created_at: '2026-01-01T00:00:00Z',
          ended_at: null,
          source_language: null,
          target_language: null,
          title: 'Standup',
          message_count: 0,
        }),
        { status: 201 },
      ),
    )

    await createSession(SESSION, 'Standup')

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/sessions')
    expect(init.method).toBe('POST')
    const headers = new Headers(init.headers)
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(JSON.parse(init.body as string)).toEqual({ title: 'Standup' })
  })

  it('resolves with the parsed JSON body on success', async () => {
    stubFetch(
      new Response(
        JSON.stringify({
          id: 's1',
          created_at: '2026-01-01T00:00:00Z',
          ended_at: null,
          source_language: 'en',
          target_language: 'es',
          title: 'Standup',
          messages: [],
        }),
        { status: 200 },
      ),
    )

    const result = await getSession(SESSION, 's1')

    expect(result.title).toBe('Standup')
    expect(result.messages).toEqual([])
  })

  it('resolves with undefined for a 204 response', async () => {
    stubFetch(new Response(null, { status: 204 }))

    await expect(deleteSession(SESSION, 's1')).resolves.toBeUndefined()
  })

  it('throws an ApiError carrying the status and detail from the response body', async () => {
    stubFetch(new Response(JSON.stringify({ detail: 'Session not found' }), { status: 404 }))

    await expect(getSession(SESSION, 'missing')).rejects.toMatchObject({
      status: 404,
      detail: 'Session not found',
    })
  })

  it('is an instance of ApiError', async () => {
    stubFetch(new Response(JSON.stringify({ detail: 'Session not found' }), { status: 404 }))

    await expect(getSession(SESSION, 'missing')).rejects.toBeInstanceOf(ApiError)
  })

  it('falls back to the status text when the error body is not JSON', async () => {
    stubFetch(new Response('not json', { status: 500, statusText: 'Internal Server Error' }))

    await expect(getSession(SESSION, 'x')).rejects.toMatchObject({
      status: 500,
      detail: 'Internal Server Error',
    })
  })
})

describe('downloadTranscript', () => {
  it('fetches the transcript with the Bearer token and returns a Blob', async () => {
    const fetchMock = stubFetch(new Response('hola\n→ hello\n', { status: 200 }))

    const blob = await downloadTranscript(SESSION, 's1', null)

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/sessions/s1/transcript')
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer tok-123')
    expect(await blob.text()).toBe('hola\n→ hello\n')
  })

  it('passes target_language when re-translating', async () => {
    const fetchMock = stubFetch(new Response('', { status: 200 }))

    await downloadTranscript(SESSION, 's1', 'fr')

    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/sessions/s1/transcript?target_language=fr')
  })

  it('throws an ApiError on failure', async () => {
    stubFetch(new Response(JSON.stringify({ detail: 'Session not found' }), { status: 404 }))

    await expect(downloadTranscript(SESSION, 'missing', null)).rejects.toMatchObject({
      status: 404,
      detail: 'Session not found',
    })
  })
})

describe('getApiUrl / getWebSocketUrl LAN host derivation', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('derives the backend host from the given location, not a hardcoded "localhost"', () => {
    const location = { hostname: '192.168.1.42', protocol: 'http:' }
    expect(getApiUrl(location)).toBe('http://192.168.1.42:8000')
    expect(getWebSocketUrl(location)).toBe('ws://192.168.1.42:8000/ws')
  })

  it('uses wss/https when the page itself was loaded over https', () => {
    const location = { hostname: 'pediluve.example', protocol: 'https:' }
    expect(getApiUrl(location)).toBe('https://pediluve.example:8000')
    expect(getWebSocketUrl(location)).toBe('wss://pediluve.example:8000/ws')
  })

  it('falls back to localhost when no location is available (e.g. non-browser context)', () => {
    expect(getApiUrl(undefined)).toBe('http://localhost:8000')
    expect(getWebSocketUrl(undefined)).toBe('ws://localhost:8000/ws')
  })

  it('VITE_API_URL / VITE_WS_URL still override the derived host when set', () => {
    vi.stubEnv('VITE_API_URL', 'https://api.example.com')
    vi.stubEnv('VITE_WS_URL', 'wss://api.example.com/ws')
    const location = { hostname: '192.168.1.42', protocol: 'http:' }
    expect(getApiUrl(location)).toBe('https://api.example.com')
    expect(getWebSocketUrl(location)).toBe('wss://api.example.com/ws')
  })
})

describe('getViewerWebSocketUrl', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('derives the /ws/view path from the given location', () => {
    const location = { hostname: '192.168.1.42', protocol: 'http:' }
    expect(getViewerWebSocketUrl(location)).toBe('ws://192.168.1.42:8000/ws/view')
  })

  it('swaps the path on VITE_WS_URL rather than ignoring it', () => {
    vi.stubEnv('VITE_WS_URL', 'wss://api.example.com/ws')
    expect(getViewerWebSocketUrl({ hostname: 'ignored', protocol: 'http:' })).toBe(
      'wss://api.example.com/ws/view',
    )
  })
})
