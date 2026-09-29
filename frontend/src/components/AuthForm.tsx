import { useState, type FormEvent } from 'react'
import { useAuth } from '../hooks/useAuth'

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
    <div className="max-w-sm mx-auto mt-16">
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm font-medium">
          Email
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            autoComplete="email"
            className="px-3 py-2 border border-ink-200 rounded-md text-base font-normal focus:border-accent-500 focus:outline-none"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            // Only enforced while registering: applying it to login too would
            // block signing in to any account whose password predates this
            // rule (or was set some other way, e.g. the dashboard/Admin API),
            // with the browser rejecting the submit before signIn() ever runs.
            minLength={mode === 'register' ? 6 : undefined}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            className="px-3 py-2 border border-ink-200 rounded-md text-base font-normal focus:border-accent-500 focus:outline-none"
          />
        </label>
        <button
          type="submit"
          disabled={submitting}
          className="bg-accent-500 text-white hover:bg-accent-600 rounded-md px-4 py-2 disabled:opacity-50"
        >
          {mode === 'login' ? 'Sign in' : 'Register'}
        </button>
      </form>

      {error && <p className="text-red-600 mt-3">{error}</p>}
      {infoMessage && <p className="text-ink-900 mt-3">{infoMessage}</p>}

      <p className="text-sm mt-3">
        {mode === 'login' ? (
          <>
            No account yet?{' '}
            <button
              type="button"
              onClick={() => switchMode('register')}
              className="bg-transparent border-none p-0 text-accent-500 underline cursor-pointer"
            >
              Register
            </button>
          </>
        ) : (
          <>
            Already have an account?{' '}
            <button
              type="button"
              onClick={() => switchMode('login')}
              className="bg-transparent border-none p-0 text-accent-500 underline cursor-pointer"
            >
              Sign in
            </button>
          </>
        )}
      </p>
    </div>
  )
}
