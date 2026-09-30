import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { ThemeToggle } from './ThemeToggle'

export function Nav() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()

  const handleSignOut = async () => {
    await signOut()
    navigate('/login')
  }

  return (
    <nav className="flex items-center gap-4 border-b border-line p-4">
      <Link
        to="/"
        className="font-semibold text-inherit no-underline hover:text-primary"
      >
        Pédiluve
      </Link>
      {user && <span className="mr-auto text-sm text-muted">{user.email}</span>}
      <ThemeToggle className={user ? '' : 'ml-auto'} />
      <button onClick={handleSignOut} className="hover:text-primary">
        Sign out
      </button>
    </nav>
  )
}
