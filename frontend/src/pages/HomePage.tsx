import { useCallback, useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { useNavigate } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { Button } from '../components/Button'
import { NewSessionModal } from '../components/NewSessionModal'
import { SessionListRow } from '../components/SessionListRow'
import { useAuth } from '../hooks/useAuth'
import { ApiError, listSessions } from '../lib/api'
import { appendSessions, removeSessionFromList, renameSessionInList } from '../lib/sessions'
import type { SessionSummary } from '../lib/types'

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
  const [creating, setCreating] = useState(false)

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
    <main className="max-w-2xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold text-fg">Your sessions</h1>
        <Button variant="primary" icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => setCreating(true)}>
          New session
        </Button>
      </div>

      {loading && <p className="text-muted">Loading…</p>}
      {error && <p className="text-danger">{error}</p>}
      {notice && (
        <p className="flex items-center gap-2 bg-subtle rounded-md px-3 py-2 text-muted mb-4">
          {notice}{' '}
          <button type="button" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </p>
      )}

      {!loading && !error && sessions.length === 0 && (
        <p className="text-muted">No sessions yet.</p>
      )}

      {sessions.length > 0 && (
        <ul className="space-y-3">
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
      <NewSessionModal session={session} open={creating} onClose={() => setCreating(false)} />
    </main>
  )
}
