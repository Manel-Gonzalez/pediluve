import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import './Nav.css'

export function Nav() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()

  const handleSignOut = async () => {
    await signOut()
    navigate('/login')
  }

  return (
    <nav className="nav">
      <span className="nav-app-name">Pédiluve</span>
      {user && <span className="nav-email">{user.email}</span>}
      <button onClick={handleSignOut}>Sign out</button>
    </nav>
  )
}
