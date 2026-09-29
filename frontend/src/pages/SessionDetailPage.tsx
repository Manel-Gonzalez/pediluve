import { useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { Link, useParams } from 'react-router-dom'
import { TranscriptRow } from '../components/TranscriptRow'
import { useAuth } from '../hooks/useAuth'
import { ApiError, getSession, translateSession } from '../lib/api'
import { DEFAULT_TARGET_LANGUAGE, SUPPORTED_LANGUAGES } from '../lib/languageControls'
import type { SessionDetail } from '../lib/types'
import './SessionDetailPage.css'

export function SessionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { session } = useAuth()
  // RequireAuth guarantees a session before this page is ever reached; the
  // route always supplies :id.
  if (!session || !id) return null
  return <SessionDetailPageContent key={id} session={session} sessionId={id} />
}

function SessionDetailPageContent({ session, sessionId }: { session: Session; sessionId: string }) {
  const [detail, setDetail] = useState<SessionDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // The language currently on display. Starts at the session's own stored
  // language (or the app default, for a session that was never translated
  // live) - never fetched from DeepL just for landing on the page.
  const [viewLanguage, setViewLanguage] = useState(DEFAULT_TARGET_LANGUAGE)
  // null = show each message's own stored translated_text (no on-demand
  // call in flight or applied); set once an on-demand translate succeeds.
  // Keyed by message id, since a session's messages don't all necessarily
  // carry the same stored target_language.
  const [translations, setTranslations] = useState<Map<string, string | null> | null>(null)
  const [translating, setTranslating] = useState(false)
  const [translateError, setTranslateError] = useState<string | null>(null)

  useEffect(() => {
    // Guards a response from a superseded fetch (id changed, but the
    // previous request was still in flight) from overwriting this render's
    // state - a real race only on a very fast back/forward through history,
    // but cheap to rule out.
    let cancelled = false
    getSession(session, sessionId)
      .then((row) => {
        if (cancelled) return
        setDetail(row)
        setViewLanguage(row.target_language ?? DEFAULT_TARGET_LANGUAGE)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true)
          return
        }
        setError(err instanceof ApiError ? err.detail : 'Could not load session')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [session, sessionId])

  const handleViewLanguageChange = async (language: string) => {
    setViewLanguage(language)
    setTranslateError(null)

    // Switching back to the session's own stored language shows the
    // messages' own translated_text again - no DeepL call needed, the data
    // is already in `detail`.
    if (language === detail?.target_language) {
      setTranslations(null)
      return
    }

    setTranslating(true)
    try {
      const response = await translateSession(session, sessionId, language)
      setTranslations(new Map(response.translations.map((t) => [t.message_id, t.translated_text])))
    } catch (err) {
      setTranslateError(err instanceof ApiError ? err.detail : 'Could not translate session')
    } finally {
      setTranslating(false)
    }
  }

  if (notFound) {
    return (
      <div className="session-detail-page">
        <p>Session not found.</p>
        <Link to="/">Back to sessions</Link>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="session-detail-page">
        <p>Loading…</p>
      </div>
    )
  }

  if (error || !detail) {
    return (
      <div className="session-detail-page">
        <p className="session-detail-error">{error ?? 'Could not load session'}</p>
        <Link to="/">Back to sessions</Link>
      </div>
    )
  }

  return (
    <div className="session-detail-page">
      <Link to="/">Back to sessions</Link>
      <h1>{detail.title ?? 'Untitled session'}</h1>
      <p className="session-detail-date">{new Date(detail.created_at).toLocaleString()}</p>

      <div className="session-detail-language">
        <label>
          View in language
          <select
            value={viewLanguage}
            disabled={translating}
            onChange={(event) => handleViewLanguageChange(event.target.value)}
          >
            {SUPPORTED_LANGUAGES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
        {translating && <span className="session-detail-translating">Translating…</span>}
      </div>
      {translateError && <p className="session-detail-error">{translateError}</p>}

      <div className="transcript">
        <div className="transcript-header">
          <span>Original</span>
          <span>Translation</span>
        </div>
        {detail.messages.map((message) => (
          <TranscriptRow
            key={message.id}
            row={
              translations
                ? {
                    ...message,
                    translated_text: translations.get(message.id) ?? null,
                    target_language: viewLanguage,
                  }
                : message
            }
          />
        ))}
      </div>
    </div>
  )
}
