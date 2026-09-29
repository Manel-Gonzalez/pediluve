import { Navigate, useLocation } from 'react-router-dom'
import { AuthForm } from '../components/AuthForm'
import { useAuth } from '../hooks/useAuth'
import { postLoginRedirect } from '../lib/routes'
import './LoginPage.css'

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
    <div className="login-page">
      <h1>Pédiluve</h1>
      <AuthForm />
    </div>
  )
}
