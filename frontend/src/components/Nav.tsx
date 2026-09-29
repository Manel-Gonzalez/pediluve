import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export function Nav() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()

  const handleSignOut = async () => {
    await signOut()
    navigate('/login')
  }

  return (
    <nav className="flex items-center gap-4 border-b border-ink-200 p-4">
      <Link
        to="/"
        className="font-semibold text-inherit no-underline hover:text-accent-500"
      >
        Pédiluve
      </Link>
      {user && <span className="mr-auto text-sm text-ink-500">{user.email}</span>}
      <button onClick={handleSignOut} className="hover:text-accent-500">
        Sign out
      </button>
    </nav>
  )
}
