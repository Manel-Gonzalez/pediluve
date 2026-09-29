import { useCallback, useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { useNavigate } from 'react-router-dom'
import { NewSessionModal } from '../components/NewSessionModal'
import { SessionListRow } from '../components/SessionListRow'
import { useAuth } from '../hooks/useAuth'
import { ApiError, listSessions } from '../lib/api'
import { appendSessions, removeSessionFromList, renameSessionInList } from '../lib/sessions'
import type { SessionSummary } from '../lib/types'
import './HomePage.css'

const PAGE_SIZE = 20

export function HomePage() {
  const { session } = useAuth()
  // RequireAuth guarantees a session before this page is ever reached - see
  // LiveSessionPage.tsx for the same split-into-Content pattern and why.
  if (!session) return null
  return <HomePageContent session={session} />
}

function HomePageContent({ session }: { session: Session }) {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const loadPage = useCallback(
    async (offset: number, append: boolean) => {
      try {
        const response = await listSessions(session, { limit: PAGE_SIZE, offset })
        setSessions((current) => (append ? appendSessions(current, response.items) : response.items))
        setHasMore(response.has_more)
        setError(null)
      } catch (err) {
        // An access token that expired between page loads (the WS handles a
        // live refresh itself, per KAN-19 - a fresh page load here has no
        // such mechanism) - send back to /login rather than showing an error
        // for a problem the user fixes by signing in again.
        if (err instanceof ApiError && err.status === 401) {
          navigate('/login')
          return
        }
        setError(err instanceof ApiError ? err.detail : 'Could not load sessions')
      } finally {
        setLoading(false)
        setLoadingMore(false)
      }
    },
    [session, navigate],
  )

  useEffect(() => {
    setLoading(true)
    loadPage(0, false)
  }, [loadPage])

  const handleLoadMore = () => {
    setLoadingMore(true)
    loadPage(sessions.length, true)
  }

  const handleRenamed = (id: string, title: string) => {
    setSessions((current) => renameSessionInList(current, id, title))
  }

  const handleDeleted = (id: string) => {
    setSessions((current) => removeSessionFromList(current, id))
  }

  const handleMissing = (id: string) => {
    setSessions((current) => removeSessionFromList(current, id))
    setNotice('That session no longer exists.')
  }

  return (
    <main className="home-page">
      <div className="home-page-header">
        <h1>Your sessions</h1>
        <NewSessionModal session={session} />
      </div>

      {loading && <p>Loading…</p>}
      {error && <p className="home-page-error">{error}</p>}
      {notice && (
        <p className="home-page-notice">
          {notice}{' '}
          <button type="button" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </p>
      )}

      {!loading && !error && sessions.length === 0 && (
        <p className="home-page-empty">No sessions yet.</p>
      )}

      {sessions.length > 0 && (
        <ul className="session-list">
          {sessions.map((item) => (
            <SessionListRow
              key={item.id}
              session={session}
              item={item}
              onRenamed={handleRenamed}
              onDeleted={handleDeleted}
              onMissing={handleMissing}
            />
          ))}
        </ul>
      )}

      {hasMore && (
        <button onClick={handleLoadMore} disabled={loadingMore}>
          {loadingMore ? 'Loading…' : 'Load more'}
        </button>
      )}
    </main>
  )
}
