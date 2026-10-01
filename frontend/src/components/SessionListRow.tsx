import { useState, type KeyboardEvent, type MouseEvent } from 'react'
import { Check, Pencil, Trash2, UserMinus, X } from 'lucide-react'
import type { Session } from '@supabase/supabase-js'
import { Link } from 'react-router-dom'
import { ApiError, deleteSession, removeGuestSession, renameSession } from '../lib/api'
import { sessionPath } from '../lib/routes'
import { validateSessionTitle } from '../lib/sessionTitle'
import { relativeTime } from '../lib/relativeTime'
import { deleteConfirmationText, formatSessionTitle } from '../lib/sessions'
import type { SessionSummary } from '../lib/types'
import { ConfirmDialog } from './ConfirmDialog'
import { IconButton } from './IconButton'

// Keeps the input focused when its own check/x buttons are pressed - blur
// cancels the edit (see onBlur below), and on a phone it would fire before
// the tap on the check lands.
const keepFocus = (event: MouseEvent) => event.preventDefault()

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
  const [confirming, setConfirming] = useState<'delete' | 'remove' | null>(null)

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

  // Both run inside ConfirmDialog: a thrown error keeps it open and shows
  // the message there. A 404 means it's already gone - drop the row.
  const handleDelete = async () => {
    try {
      await deleteSession(session, item.id)
      onDeleted(item.id)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        onMissing(item.id)
        return
      }
      throw err
    }
  }

  // Distinct from handleDelete: a guest never owns the session (KAN-59's
  // RLS is owner-only for delete regardless), this only removes *their own*
  // session_guests row - the session itself, and everyone else's access to
  // it, is untouched.
  const handleRemoveGuestSession = async () => {
    try {
      await removeGuestSession(session, item.id)
      onDeleted(item.id)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        onMissing(item.id)
        return
      }
      throw err
    }
  }

  return (
    <li className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-subtle/60">
      {isEditing ? (
        <div className="flex flex-1 flex-col gap-1">
          <div className="flex items-center gap-1">
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
              aria-label="Session title"
              className="min-w-0 flex-1 rounded-lg border border-line px-2 py-1 text-base focus:border-primary focus:outline-none"
            />
            <IconButton label="Save title" onMouseDown={keepFocus} onClick={saveRename} disabled={pending}>
              <Check className="h-4 w-4" aria-hidden />
            </IconButton>
            <IconButton label="Cancel rename" onMouseDown={keepFocus} onClick={cancelEditing} disabled={pending}>
              <X className="h-4 w-4" aria-hidden />
            </IconButton>
          </div>
          {error && <span className="text-sm text-danger">{error}</span>}
        </div>
      ) : (
        <Link to={sessionPath(item.id)} className="flex min-w-0 flex-1 flex-col gap-1 rounded-md text-inherit no-underline">
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate font-medium text-fg">{formatSessionTitle(item)}</span>
            {item.role === 'guest' && (
              <span className="shrink-0 rounded-full bg-highlight px-2 py-0.5 text-xs font-medium text-highlight-fg">
                Guest
              </span>
            )}
          </span>
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
            <time dateTime={item.created_at} title={new Date(item.created_at).toLocaleString()}>
              {relativeTime(item.created_at)}
            </time>
            <span aria-hidden className="hidden sm:inline">·</span>
            <span className="rounded border border-line px-1.5 text-xs font-medium uppercase tracking-wide">
              {item.source_language ?? 'auto'} → {item.target_language ?? '?'}
            </span>
            <span aria-hidden className="hidden sm:inline">·</span>
            <span className="tabular-nums">
              {item.message_count} message{item.message_count === 1 ? '' : 's'}
            </span>
          </span>
        </Link>
      )}
      <div className="flex shrink-0 gap-1">
        {item.role === 'guest' ? (
          <IconButton label="Remove from my sessions" tone="danger" onClick={() => setConfirming('remove')}>
            <UserMinus className="h-4 w-4" aria-hidden />
          </IconButton>
        ) : (
          <>
            <IconButton label="Rename session" onClick={startEditing} disabled={isEditing}>
              <Pencil className="h-4 w-4" aria-hidden />
            </IconButton>
            <IconButton label="Delete session" tone="danger" onClick={() => setConfirming('delete')}>
              <Trash2 className="h-4 w-4" aria-hidden />
            </IconButton>
          </>
        )}
      </div>
      <ConfirmDialog
        open={confirming === 'delete'}
        onClose={() => setConfirming(null)}
        title="Delete this session?"
        description={deleteConfirmationText(item)}
        confirmLabel="Delete"
        pendingLabel="Deleting…"
        tone="danger"
        onConfirm={handleDelete}
      />
      <ConfirmDialog
        open={confirming === 'remove'}
        onClose={() => setConfirming(null)}
        title="Remove from your sessions?"
        description={`"${formatSessionTitle(item)}" will disappear from your list. The session itself stays with its owner, and you can add it again from its share link.`}
        confirmLabel="Remove"
        pendingLabel="Removing…"
        tone="danger"
        onConfirm={handleRemoveGuestSession}
      />
    </li>
  )
}
