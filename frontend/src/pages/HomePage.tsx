import { useCallback, useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Mic, Plus, X } from 'lucide-react'
import { Button } from '../components/Button'
import { IconButton } from '../components/IconButton'
import { NewSessionModal } from '../components/NewSessionModal'
import { SessionListRow } from '../components/SessionListRow'
import { useAuth } from '../hooks/useAuth'
import { ApiError, listSessions } from '../lib/api'
import {
  PAGE_SIZE,
  clampPage,
  offsetForPage,
  pageAfterRemoval,
  pageCount,
  parsePageParam,
  rangeLabel,
} from '../lib/pagination'
import { renameSessionInList } from '../lib/sessions'
import type { SessionSummary } from '../lib/types'

export function HomePage() {
  const { session } = useAuth()
  // RequireAuth guarantees a session before this page is ever reached - see
  // LiveSessionPage.tsx for the same split-into-Content pattern and why.
  if (!session) return null
  return <HomePageContent session={session} />
}

function HomePageContent({ session }: { session: Session }) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const page = parsePageParam(searchParams.get('page'))
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  // Bumped to refetch the current page, e.g. after a delete so the next
  // session slides up into the freed slot.
  const [reloadKey, setReloadKey] = useState(0)

  // `replace` for corrections (clamping, a removal stepping back) so they
  // don't leave a dead entry in history; a push for Prev/Next.
  const goToPage = useCallback(
    (next: number, replace = false) => {
      setSearchParams(next === 1 ? {} : { page: String(next) }, { replace })
    },
    [setSearchParams],
  )

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    listSessions(session, { limit: PAGE_SIZE, offset: offsetForPage(page, PAGE_SIZE) })
      .then((response) => {
        if (cancelled) return
        const lastPage = pageCount(response.total, PAGE_SIZE)
        // ?page=999, or a page emptied since the link was made.
        if (page > lastPage) {
          goToPage(clampPage(page, lastPage), true)
          return
        }
        setSessions(response.items)
        setTotal(response.total)
        setError(null)
        setLoading(false)
      })
      .catch((err) => {
        if (cancelled) return
        // An access token that expired between page loads (the WS handles a
        // live refresh itself, per KAN-19 - a fresh page load here has no
        // such mechanism) - send back to /login rather than showing an error
        // for a problem the user fixes by signing in again.
        if (err instanceof ApiError && err.status === 401) {
          navigate('/login')
          return
        }
        setError(err instanceof ApiError ? err.detail : 'Could not load sessions')
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [session, page, reloadKey, navigate, goToPage])

  const handleRenamed = (id: string, title: string) => {
    setSessions((current) => renameSessionInList(current, id, title))
  }

  const handleRemoved = (id: string, message?: string) => {
    if (message) setNotice(message)
    setSessions((current) => current.filter((item) => item.id !== id))
    const next = pageAfterRemoval(page, total - 1, PAGE_SIZE)
    if (next !== page) goToPage(next, true)
    else setReloadKey((key) => key + 1)
  }

  const pages = pageCount(total, PAGE_SIZE)
  const isEmpty = !loading && !error && total === 0

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Sessions</h1>
          <p className="mt-1 text-sm tabular-nums text-muted">
            {loading ? ' ' : `${total} session${total === 1 ? '' : 's'}`}
          </p>
        </div>
        <Button variant="primary" icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => setCreating(true)}>
          New session
        </Button>
      </div>

      {notice && (
        <div role="status" className="mb-4 flex items-center gap-2 rounded-lg bg-subtle py-1 pl-4 pr-1 text-sm text-muted">
          <span className="flex-1">{notice}</span>
          <IconButton label="Dismiss" onClick={() => setNotice(null)}>
            <X className="h-4 w-4" aria-hidden />
          </IconButton>
        </div>
      )}
      {error && (
        <p role="alert" className="mb-4 rounded-lg bg-danger-soft px-4 py-3 text-sm text-danger">
          {error}
        </p>
      )}

      {loading && !error && <SkeletonList />}

      {isEmpty && (
        <div className="flex flex-col items-center rounded-xl border border-dashed border-line px-6 py-16 text-center">
          <span className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-full bg-highlight text-highlight-fg">
            <Mic className="h-6 w-6" aria-hidden />
          </span>
          <h2 className="text-lg font-semibold tracking-tight">No sessions yet</h2>
          <p className="mb-6 mt-1 max-w-sm text-sm text-muted">
            Start one, speak, and watch it transcribed and translated live - then share it with a QR code.
          </p>
          <Button variant="primary" icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => setCreating(true)}>
            Start your first session
          </Button>
        </div>
      )}

      {!loading && sessions.length > 0 && (
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
          {sessions.map((item) => (
            <SessionListRow
              key={item.id}
              session={session}
              item={item}
              onRenamed={handleRenamed}
              onDeleted={(id) => handleRemoved(id)}
              onMissing={(id) => handleRemoved(id, 'That session no longer exists.')}
            />
          ))}
        </ul>
      )}

      {!loading && total > 0 && (
        <nav aria-label="Pagination" className="mt-4 flex items-center justify-between gap-4 text-sm text-muted">
          <span className="tabular-nums">{rangeLabel(page, PAGE_SIZE, total)}</span>
          {pages > 1 && (
            <div className="flex items-center gap-1">
              <IconButton label="Previous page" onClick={() => goToPage(page - 1)} disabled={page <= 1}>
                <ChevronLeft className="h-5 w-5" aria-hidden />
              </IconButton>
              <span className="px-2 tabular-nums" aria-current="page">
                Page {page} of {pages}
              </span>
              <IconButton label="Next page" onClick={() => goToPage(page + 1)} disabled={page >= pages}>
                <ChevronRight className="h-5 w-5" aria-hidden />
              </IconButton>
            </div>
          )}
        </nav>
      )}

      <NewSessionModal session={session} open={creating} onClose={() => setCreating(false)} />
    </main>
  )
}

function SkeletonList() {
  return (
    <ul aria-hidden className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
      {Array.from({ length: 5 }, (_, i) => (
        <li key={i} className="flex items-center gap-4 px-4 py-4">
          <div className="flex-1 space-y-2">
            <div className="h-4 w-1/3 rounded bg-subtle motion-safe:animate-pulse" />
            <div className="h-3 w-1/2 rounded bg-subtle motion-safe:animate-pulse" />
          </div>
        </li>
      ))}
    </ul>
  )
}
