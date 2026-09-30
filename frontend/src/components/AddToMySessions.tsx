import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { addGuestSession } from '../lib/api'

// "Add to my sessions" (KAN-62): a signed-in guest saves a live/past
// session to their own account from its share link. Signed out, this is
// just a sign-in link that returns here afterward (postLoginRedirect
// already supports an arbitrary "from" path, same mechanism RequireAuth
// uses for its own redirects).
export function AddToMySessions({
  shareToken,
  targetLanguage,
}: {
  shareToken: string
  targetLanguage: string
}) {
  const { session } = useAuth()
  const location = useLocation()
  const [status, setStatus] = useState<'idle' | 'saving' | 'added' | 'error'>('idle')

  if (!session) {
    return (
      <Link
        to="/login"
        state={{ from: { pathname: location.pathname } }}
        className="w-fit text-xs text-accent-500 hover:text-accent-600"
      >
        Sign in to add this session to your account
      </Link>
    )
  }

  if (status === 'added') {
    return <p className="text-xs text-ink-500">Added to your sessions.</p>
  }

  const handleClick = async () => {
    setStatus('saving')
    try {
      await addGuestSession(session, shareToken, targetLanguage)
      setStatus('added')
    } catch {
      setStatus('error')
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={status === 'saving'}
      className="w-fit rounded border border-ink-200 px-2 py-1 text-xs font-medium text-ink-900 hover:border-ink-300 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {status === 'saving' ? 'Adding…' : status === 'error' ? 'Retry' : 'Add to my sessions'}
    </button>
  )
}
