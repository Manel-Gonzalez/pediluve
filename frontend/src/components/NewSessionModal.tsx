import { useRef, useState, type FormEvent } from 'react'
import type { Session } from '@supabase/supabase-js'
import { useNavigate } from 'react-router-dom'
import { ApiError, createSession } from '../lib/api'
import { liveSessionPath } from '../lib/routes'
import { validateSessionTitle } from '../lib/sessionTitle'

export function NewSessionModal({ session }: { session: Session }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  // A ref, not just the `pending` state below: two rapid clicks can both
  // read `pending` as still false before React has re-rendered with the
  // disabled button, since setState doesn't take effect synchronously. This
  // is checked and set before any await, so the second click always loses.
  const pendingRef = useRef(false)
  const [title, setTitle] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const navigate = useNavigate()

  const openModal = () => {
    setTitle('')
    setError(null)
    dialogRef.current?.showModal()
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
      dialogRef.current?.close()
      navigate(liveSessionPath(row.id))
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not create session')
    } finally {
      pendingRef.current = false
      setPending(false)
    }
  }

  return (
    <>
      <button
        onClick={openModal}
        className="bg-primary text-on-primary hover:bg-primary-hover rounded-md px-4 py-2"
      >
        New session
      </button>
      {/* Esc closes a native <dialog> on its own (fires "cancel" then
          "close") - no extra handling needed for that part of the spec. */}
      <dialog
        ref={dialogRef}
        className="bg-surface text-fg rounded-lg shadow-lg p-6 min-w-80 backdrop:bg-black/40"
      >
        <form onSubmit={handleSubmit} className="flex flex-col">
          <h2 className="text-xl font-medium mt-0 mb-3">New session</h2>
          <label className="flex flex-col gap-1 text-sm font-medium mb-4">
            Title
            <input
              autoFocus
              maxLength={120}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              disabled={pending}
              className="px-3 py-2 border border-line rounded-md text-base font-normal focus:border-primary focus:outline-none"
            />
          </label>
          {error && <p className="text-danger mb-4">{error}</p>}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => dialogRef.current?.close()}
              disabled={pending}
              className="px-4 py-2 rounded-md border border-line disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={pending}
              className="bg-primary text-on-primary hover:bg-primary-hover rounded-md px-4 py-2 disabled:opacity-50"
            >
              {pending ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>
      </dialog>
    </>
  )
}
