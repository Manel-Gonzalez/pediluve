import { Check, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { addGuestSession } from '../lib/api'
import { Button, FOCUS_RING } from './Button'

// "Add to my sessions" (KAN-62): a signed-in guest saves a live/past
// session to their own account from its share link. Signed out, this is
// just a sign-in link that returns here afterward (postLoginRedirect
// already supports an arbitrary "from" path, same mechanism RequireAuth
// uses for its own redirects).
export function AddToMySessions({
  shareToken,
  targetLanguage,
  compact = false,
}: {
  shareToken: string
  targetLanguage: string
  // A short "Save" for the viewer's control row (KAN-80); the full wording
  // stays in the tooltip and in the session-ended notice.
  compact?: boolean
}) {
  const { session } = useAuth()
  const location = useLocation()
  const [status, setStatus] = useState<'idle' | 'saving' | 'added' | 'error'>('idle')

  if (!session) {
    return (
      <Link
        to="/login"
        state={{ from: { pathname: location.pathname } }}
        title="Sign in to add this session to your account"
        className={`inline-flex h-8 items-center gap-1.5 rounded-lg px-2 text-sm font-medium text-primary hover:bg-highlight ${FOCUS_RING}`}
      >
        <UserPlus className="h-4 w-4" aria-hidden />
        {compact ? 'Save' : 'Sign in to save it to your sessions'}
      </Link>
    )
  }

  if (status === 'added') {
    return (
      <p role="status" className="inline-flex h-8 items-center gap-1.5 px-2 text-sm text-muted">
        <Check className="h-4 w-4 text-primary" aria-hidden />
        {compact ? 'Saved' : 'Added to your sessions'}
      </p>
    )
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
    <Button
      size="sm"
      onClick={handleClick}
      loading={status === 'saving'}
      icon={<UserPlus className="h-4 w-4" aria-hidden />}
    >
      {status === 'saving' ? 'Adding…' : status === 'error' ? 'Retry' : compact ? 'Save' : 'Add to my sessions'}
    </Button>
  )
}
