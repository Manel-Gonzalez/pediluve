import { Navigate, useLocation } from 'react-router-dom'
import { AuthForm } from '../components/AuthForm'
import { ThemeToggle } from '../components/ThemeToggle'
import { useAuth } from '../hooks/useAuth'
import { postLoginRedirect } from '../lib/routes'

export function LoginPage() {
  const { user, loading } = useAuth()
  const location = useLocation()

  // Same reasoning as RequireAuth: don't show the form only to immediately
  // replace it once the restored session resolves.
  if (loading) return null

  if (user) {
    return <Navigate to={postLoginRedirect(location.state)} replace />
  }

  return (
    <div className="relative px-4 py-12 text-center">
      <ThemeToggle className="absolute right-4 top-4" />
      <h1 className="text-3xl font-semibold text-fg">Pédiluve</h1>
      <AuthForm />
    </div>
  )
}
