import { useState, type KeyboardEvent } from 'react'
import type { Session } from '@supabase/supabase-js'
import { Link } from 'react-router-dom'
import { ApiError, deleteSession, removeGuestSession, renameSession } from '../lib/api'
import { sessionPath } from '../lib/routes'
import { validateSessionTitle } from '../lib/sessionTitle'
import { formatSessionTitle } from '../lib/sessions'
import type { SessionSummary } from '../lib/types'

type SessionListRowProps = {
  session: Session
  item: SessionSummary
  onRenamed: (id: string, title: string) => void
  onDeleted: (id: string) => void
  onMissing: (id: string) => void
}

export function SessionListRow({ session, item, onRenamed, onDeleted, onMissing }: SessionListRowProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [draftTitle, setDraftTitle] = useState(item.title ?? '')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const startEditing = () => {
    setDraftTitle(item.title ?? '')
    setError(null)
    setIsEditing(true)
  }

  const cancelEditing = () => {
    setIsEditing(false)
    setError(null)
  }

  const saveRename = async () => {
    const validation = validateSessionTitle(draftTitle)
    if (!validation.ok) {
      setError(validation.error)
      return
    }

    setPending(true)
    setError(null)
    try {
      const updated = await renameSession(session, item.id, validation.title)
      onRenamed(item.id, updated.title ?? validation.title)
      setIsEditing(false)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        onMissing(item.id)
        return
      }
      setError(err instanceof ApiError ? err.detail : 'Could not rename session')
    } finally {
      setPending(false)
    }
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      saveRename()
    } else if (event.key === 'Escape') {
      event.preventDefault()
      cancelEditing()
    }
  }

  const handleDelete = async () => {
    const confirmed = window.confirm(
      `Delete "${formatSessionTitle(item)}" and its ${item.message_count} message${
        item.message_count === 1 ? '' : 's'
      }?`,
    )
    if (!confirmed) return

    try {
      await deleteSession(session, item.id)
      onDeleted(item.id)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        onMissing(item.id)
      }
      // Any other failure leaves the row in place - Delete stays clickable
      // to retry, no extra error UI needed for this rare path.
    }
  }

  // Distinct from handleDelete: a guest never owns the session (KAN-59's
  // RLS is owner-only for delete regardless), this only removes *their own*
  // session_guests row - the session itself, and everyone else's access to
  // it, is untouched.
  const handleRemoveGuestSession = async () => {
    const confirmed = window.confirm(`Remove "${formatSessionTitle(item)}" from your sessions?`)
    if (!confirmed) return

    try {
      await removeGuestSession(session, item.id)
      onDeleted(item.id)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        onMissing(item.id)
      }
    }
  }

  return (
    <li className="flex items-center justify-between gap-4 rounded-lg border border-line p-4 transition-shadow hover:shadow-md hover:border-primary/40">
      {isEditing ? (
        <div className="flex flex-col gap-1 flex-1">
          <input
            autoFocus
            maxLength={120}
            value={draftTitle}
            disabled={pending}
            onChange={(event) => setDraftTitle(event.target.value)}
            onKeyDown={handleKeyDown}
            // A click away from the input cancels rather than saves -
            // Enter is the only way to commit, so an accidental blur can't
            // silently rename the session.
            onBlur={() => !pending && cancelEditing()}
            className="px-2 py-1 text-base border border-line rounded-md"
          />
          {error && <span className="text-sm text-danger">{error}</span>}
        </div>
      ) : (
        <Link to={sessionPath(item.id)} className="flex flex-col gap-1 text-inherit no-underline">
          <span className="flex items-center gap-2 font-semibold text-fg">
            {formatSessionTitle(item)}
            {item.role === 'guest' && (
              <span className="inline-block rounded bg-highlight px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-highlight-fg">
                Guest
              </span>
            )}
          </span>
          <span className="text-sm text-muted">
            {new Date(item.created_at).toLocaleString()}
            {' · '}
            {item.source_language ?? '?'} → {item.target_language ?? '?'}
            {' · '}
            {item.message_count} message{item.message_count === 1 ? '' : 's'}
          </span>
        </Link>
      )}
      <div className="flex gap-2 flex-shrink-0">
        {item.role === 'guest' ? (
          <button
            type="button"
            onClick={handleRemoveGuestSession}
            className="px-3 py-1 text-sm rounded-md border border-line text-danger hover:bg-danger-soft"
          >
            Remove
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={startEditing}
              disabled={isEditing}
              className="px-3 py-1 text-sm rounded-md border border-primary text-primary hover:bg-highlight disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Rename
            </button>
            <button
              type="button"
              onClick={handleDelete}
              className="px-3 py-1 text-sm rounded-md border border-line text-danger hover:bg-danger-soft"
            >
              Delete
            </button>
          </>
        )}
      </div>
    </li>
  )
}
