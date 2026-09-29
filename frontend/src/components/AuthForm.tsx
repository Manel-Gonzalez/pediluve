import { useState, type FormEvent } from 'react'
import { useAuth } from '../hooks/useAuth'
import './AuthForm.css'

type Mode = 'login' | 'register'

export function AuthForm() {
  const { signIn, signUp } = useAuth()
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Set only on a successful register whose signUp() returned no session
  // (email confirmation pending) - distinct from `error`, since it's not a
  // failure, just a different successful outcome the form has to show.
  const [infoMessage, setInfoMessage] = useState<string | null>(null)

  const switchMode = (next: Mode) => {
    setMode(next)
    setError(null)
    setInfoMessage(null)
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setInfoMessage(null)
    setSubmitting(true)
    try {
      if (mode === 'login') {
        const { error: signInError } = await signIn(email, password)
        if (signInError) setError(signInError)
        return
      }

      const { error: signUpError, needsEmailConfirmation } = await signUp(email, password)
      if (signUpError) {
        setError(signUpError)
      } else if (needsEmailConfirmation) {
        setInfoMessage('Check your inbox to confirm your email, then sign in.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-form">
      <form onSubmit={handleSubmit}>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            autoComplete="email"
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={6}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          />
        </label>
        <button type="submit" disabled={submitting}>
          {mode === 'login' ? 'Sign in' : 'Register'}
        </button>
      </form>

      {error && <p className="auth-form-error">{error}</p>}
      {infoMessage && <p className="auth-form-info">{infoMessage}</p>}

      <p className="auth-form-toggle">
        {mode === 'login' ? (
          <>
            No account yet?{' '}
            <button type="button" onClick={() => switchMode('register')}>
              Register
            </button>
          </>
        ) : (
          <>
            Already have an account?{' '}
            <button type="button" onClick={() => switchMode('login')}>
              Sign in
            </button>
          </>
        )}
      </p>
    </div>
  )
}
