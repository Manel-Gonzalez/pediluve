import { useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { Link, useParams } from 'react-router-dom'
import { TranscriptRow } from '../components/TranscriptRow'
import { useAuth } from '../hooks/useAuth'
import { ApiError, downloadTranscript, getSession, translateSession } from '../lib/api'
import { saveBlob, transcriptFilename } from '../lib/download'
import { DEFAULT_TARGET_LANGUAGE, SUPPORTED_LANGUAGES } from '../lib/languageControls'
import { initialViewLanguage } from '../lib/sessions'
import type { SessionDetail, TranslateResponse } from '../lib/types'

function toTranslationMap(response: TranslateResponse): Map<string, string | null> {
  return new Map(response.translations.map((t) => [t.message_id, t.translated_text]))
}

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
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)

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
        const { language, needsTranslation } = initialViewLanguage(row)
        setViewLanguage(language)
        // Only ever true for a guest who picked their own language when
        // saving the session - the one case landing here spends a DeepL
        // call, since that's the language they asked to read it in.
        if (!needsTranslation) return
        setTranslating(true)
        translateSession(session, sessionId, language)
          .then((response) => {
            if (!cancelled) setTranslations(toTranslationMap(response))
          })
          .catch((err: unknown) => {
            if (!cancelled) {
              setTranslateError(err instanceof ApiError ? err.detail : 'Could not translate session')
            }
          })
          .finally(() => {
            if (!cancelled) setTranslating(false)
          })
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
      setTranslations(toTranslationMap(response))
    } catch (err) {
      setTranslateError(err instanceof ApiError ? err.detail : 'Could not translate session')
    } finally {
      setTranslating(false)
    }
  }

  // Downloads what's on screen: the on-demand translation if one is being
  // shown, otherwise each message's own stored translation (null language).
  const handleDownload = async () => {
    if (!detail) return
    const language = translations ? viewLanguage : null
    setDownloading(true)
    setDownloadError(null)
    try {
      const blob = await downloadTranscript(session, sessionId, language)
      saveBlob(blob, transcriptFilename(detail.title, language ?? detail.target_language))
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.detail : 'Could not download transcript')
    } finally {
      setDownloading(false)
    }
  }

  if (notFound) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-8">
        <p>Session not found.</p>
        <Link to="/" className="text-primary hover:text-primary-hover">
          Back to sessions
        </Link>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-8">
        <p className="text-muted">Loading…</p>
      </div>
    )
  }

  if (error || !detail) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-8">
        <p className="text-danger">{error ?? 'Could not load session'}</p>
        <Link to="/" className="text-primary hover:text-primary-hover">
          Back to sessions
        </Link>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <Link to="/" className="text-sm text-primary hover:text-primary-hover">
        Back to sessions
      </Link>
      <h1 className="mt-2 text-2xl font-semibold text-fg">
        {detail.title ?? 'Untitled session'}
      </h1>
      <p className="mt-1 text-sm text-muted">{new Date(detail.created_at).toLocaleString()}</p>

      <div className="my-4 flex items-center gap-4">
        <label className="flex flex-col gap-1 text-sm text-fg">
          View in language
          <select
            value={viewLanguage}
            disabled={translating}
            onChange={(event) => handleViewLanguageChange(event.target.value)}
            className="rounded border border-line px-2 py-1 text-sm disabled:cursor-not-allowed disabled:opacity-50"
          >
            {SUPPORTED_LANGUAGES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
        {translating && <span className="text-sm italic text-muted">Translating…</span>}
        <button
          onClick={handleDownload}
          disabled={downloading || translating || detail.messages.length === 0}
          className="ml-auto self-end rounded border border-line px-3 py-1.5 text-sm font-medium text-fg hover:border-line-strong disabled:cursor-not-allowed disabled:opacity-50"
        >
          {downloading ? 'Downloading…' : 'Download transcript'}
        </button>
      </div>
      {translateError && <p className="text-danger">{translateError}</p>}
      {downloadError && <p className="text-danger">{downloadError}</p>}

      <div className="my-4 flex flex-col gap-3">
        {detail.messages.map((message) => (
          <TranscriptRow
            key={message.id}
            sourceLanguage={detail.source_language}
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
