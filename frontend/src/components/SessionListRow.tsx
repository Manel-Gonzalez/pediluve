import { useState, type KeyboardEvent } from 'react'
import type { Session } from '@supabase/supabase-js'
import { Link } from 'react-router-dom'
import { ApiError, deleteSession, renameSession } from '../lib/api'
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

  return (
    <li className="session-list-row">
      {isEditing ? (
        <div className="session-list-edit">
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
          />
          {error && <span className="session-list-error">{error}</span>}
        </div>
      ) : (
        <Link to={sessionPath(item.id)} className="session-list-link">
          <span className="session-list-title">{formatSessionTitle(item)}</span>
          <span className="session-list-meta">
            {new Date(item.created_at).toLocaleString()}
            {' · '}
            {item.source_language ?? '?'} → {item.target_language ?? '?'}
            {' · '}
            {item.message_count} message{item.message_count === 1 ? '' : 's'}
          </span>
        </Link>
      )}
      <div className="session-list-actions">
        <button type="button" onClick={startEditing} disabled={isEditing}>
          Rename
        </button>
        <button type="button" onClick={handleDelete}>
          Delete
        </button>
      </div>
    </li>
  )
}
