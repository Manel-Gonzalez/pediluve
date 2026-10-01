import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { validateRegistration, type RegistrationCheck } from '../lib/authForm'
import { Button, FOCUS_RING } from './Button'
import { IconButton } from './IconButton'

type Mode = 'login' | 'register'
type FieldError = Extract<RegistrationCheck, { ok: false }>

const INPUT =
  'h-11 w-full rounded-lg border border-line px-3 text-base placeholder:text-muted/70 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30 aria-[invalid=true]:border-danger'

export function AuthForm() {
  const { signIn, signUp } = useAuth()
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldError, setFieldError] = useState<FieldError | null>(null)
  // Set only on a successful register whose signUp() returned no session
  // (email confirmation pending) - distinct from `error`, since it's not a
  // failure, just a different successful outcome the form has to show.
  const [infoMessage, setInfoMessage] = useState<string | null>(null)
  const ids = { password: useId(), confirm: useId(), fieldError: useId() }

  const switchMode = (next: Mode) => {
    setMode(next)
    setConfirmPassword('')
    setError(null)
    setFieldError(null)
    setInfoMessage(null)
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setFieldError(null)
    setInfoMessage(null)

    if (mode === 'register') {
      const check = validateRegistration({ password, confirmPassword })
      if (!check.ok) {
        setFieldError(check)
        return
      }
    }

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

  const errorFor = (field: FieldError['field']) =>
    fieldError?.field === field
      ? { 'aria-invalid': true as const, 'aria-describedby': ids.fieldError }
      : {}

  const visibilityToggle = (
    <IconButton
      label={showPassword ? 'Hide password' : 'Show password'}
      onClick={() => setShowPassword((shown) => !shown)}
      className="absolute right-1 top-1/2 -translate-y-1/2"
    >
      {showPassword ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
    </IconButton>
  )

  return (
    <div className="w-full max-w-sm">
      <h1 className="text-2xl font-semibold tracking-tight">
        {mode === 'login' ? 'Welcome back' : 'Create your account'}
      </h1>
      <p className="mb-6 mt-1 text-sm text-muted">
        {mode === 'login'
          ? 'Sign in to record, translate and share your sessions.'
          : 'Free to try - all you need is an email and a password.'}
      </p>

      <div role="group" aria-label="Account" className="mb-6 grid grid-cols-2 gap-1 rounded-lg bg-subtle p-1">
        <ModeTab active={mode === 'login'} onClick={() => switchMode('login')}>
          Sign in
        </ModeTab>
        <ModeTab active={mode === 'register'} onClick={() => switchMode('register')}>
          Create account
        </ModeTab>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate={mode === 'register'}>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Email
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            autoComplete="email"
            placeholder="you@example.com"
            className={INPUT}
          />
        </label>

        <div className="flex flex-col gap-1.5">
          <label htmlFor={ids.password} className="text-sm font-medium">
            Password
          </label>
          <div className="relative">
            <input
              id={ids.password}
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              className={`${INPUT} pr-11`}
              {...errorFor('password')}
            />
            {visibilityToggle}
          </div>
        </div>

        {mode === 'register' && (
          <div className="flex flex-col gap-1.5">
            <label htmlFor={ids.confirm} className="text-sm font-medium">
              Confirm password
            </label>
            <input
              id={ids.confirm}
              type={showPassword ? 'text' : 'password'}
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
              autoComplete="new-password"
              className={INPUT}
              {...errorFor('confirmPassword')}
            />
          </div>
        )}

        {fieldError && (
          <p id={ids.fieldError} role="alert" className="-mt-2 text-sm text-danger">
            {fieldError.error}
          </p>
        )}

        <Button type="submit" variant="primary" loading={submitting} className="mt-2 h-11 w-full">
          {mode === 'login' ? 'Sign in' : 'Create account'}
        </Button>
      </form>

      {error && (
        <p role="alert" className="mt-4 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}
      {infoMessage && (
        <p role="status" className="mt-4 rounded-lg bg-highlight px-3 py-2 text-sm text-highlight-fg">
          {infoMessage}
        </p>
      )}
    </div>
  )
}

function ModeTab({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`h-9 rounded-md text-sm font-medium transition-colors ${FOCUS_RING} ${
        active ? 'bg-surface text-fg shadow-sm' : 'text-muted hover:text-fg'
      }`}
    >
      {children}
    </button>
  )
}
