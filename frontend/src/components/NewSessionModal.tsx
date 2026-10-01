import { useRef, useState, type FormEvent } from 'react'
import type { Session } from '@supabase/supabase-js'
import { useNavigate } from 'react-router-dom'
import { ApiError, createSession } from '../lib/api'
import { liveSessionPath } from '../lib/routes'
import { validateSessionTitle } from '../lib/sessionTitle'
import { Button } from './Button'
import { Dialog } from './Dialog'

// Controlled by the page (KAN-77) so more than one place can open it: the
// header's "New session" button and the empty state's call to action.
export function NewSessionModal({
  session,
  open,
  onClose,
}: {
  session: Session
  open: boolean
  onClose: () => void
}) {
  // A ref, not just the `pending` state below: two rapid clicks can both
  // read `pending` as still false before React has re-rendered with the
  // disabled button, since setState doesn't take effect synchronously. This
  // is checked and set before any await, so the second click always loses.
  const pendingRef = useRef(false)
  const [title, setTitle] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const navigate = useNavigate()

  const handleClose = () => {
    setTitle('')
    setError(null)
    onClose()
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (pendingRef.current) return

    const validation = validateSessionTitle(title)
    if (!validation.ok) {
      setError(validation.error)
      return
    }

    pendingRef.current = true
    setPending(true)
    setError(null)
    try {
      const row = await createSession(session, validation.title)
      navigate(liveSessionPath(row.id))
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not create session')
    } finally {
      pendingRef.current = false
      setPending(false)
    }
  }

  return (
    <Dialog open={open} onClose={handleClose} title="New session" dismissible={!pending}>
      <form onSubmit={handleSubmit} className="flex flex-col">
        <p className="mb-4 text-sm text-muted">Give it a name - you can rename it later.</p>
        <label className="mb-4 flex flex-col gap-1.5 text-sm font-medium">
          Title
          <input
            data-autofocus
            maxLength={120}
            value={title}
            placeholder="e.g. Weekly standup"
            onChange={(event) => setTitle(event.target.value)}
            disabled={pending}
            aria-invalid={error ? true : undefined}
            className="h-10 rounded-lg border border-line px-3 text-base font-normal placeholder:text-muted/70 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        </label>
        {error && (
          <p role="alert" className="mb-4 text-sm text-danger">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button onClick={handleClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={pending}>
            {pending ? 'Creating…' : 'Create and start'}
          </Button>
        </div>
      </form>
    </Dialog>
  )
}
