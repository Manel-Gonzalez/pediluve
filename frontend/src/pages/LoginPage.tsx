import { Navigate, useLocation } from 'react-router-dom'
import { AuthForm } from '../components/AuthForm'
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
    <div className="px-4 py-12 text-center">
      <h1 className="text-3xl font-semibold text-ink-900">Pédiluve</h1>
      <AuthForm />
    </div>
  )
}
