import { LogOut } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { IconButton } from './IconButton'
import { LogoMark } from './LogoMark'
import { ThemeToggle } from './ThemeToggle'

export function Nav() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()

  const handleSignOut = async () => {
    await signOut()
    navigate('/login')
  }

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-canvas/80 backdrop-blur">
      <nav className="mx-auto flex h-14 max-w-5xl items-center gap-2 px-4 sm:px-6">
        <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight text-fg no-underline">
          <LogoMark />
          Pédiluve
        </Link>
        <div className="ml-auto flex items-center gap-1">
          {user && <span className="mr-2 hidden text-sm text-muted sm:inline">{user.email}</span>}
          <ThemeToggle />
          <IconButton label="Sign out" onClick={handleSignOut}>
            <LogOut className="h-5 w-5" aria-hidden />
          </IconButton>
        </div>
      </nav>
    </header>
  )
}
