import { useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { Link, useParams } from 'react-router-dom'
import { TranscriptRow } from '../components/TranscriptRow'
import { useAuth } from '../hooks/useAuth'
import { ApiError, getSession } from '../lib/api'
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

      <div className="transcript">
        <div className="transcript-header">
          <span>Original</span>
          <span>Translation</span>
        </div>
        {detail.messages.map((message) => (
          <TranscriptRow key={message.id} row={message} />
        ))}
      </div>
    </div>
  )
}
