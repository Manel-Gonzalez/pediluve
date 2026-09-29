import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { Nav } from './Nav'

// A layout route: mounted once above every authenticated route (today just
// "/"), so Nav shows up on all of them without each page rendering it itself
// - Phase 4 adds more protected routes under the same guard.
export function RequireAuth() {
  const { user, loading } = useAuth()
  const location = useLocation()

  // Nothing yet, not the login form: the initial getSession() (useAuth) may
  // still resolve to a real session, and redirecting here would be a flash
  // of the login page that immediately bounces back on every reload.
  if (loading) return null

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return (
    <>
      <Nav />
      <Outlet />
    </>
  )
}
