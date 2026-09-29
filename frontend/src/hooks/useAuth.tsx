import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { Session, User } from '@supabase/supabase-js'
import { supabase } from '../lib/supabase'
import { describeAuthError } from '../lib/authErrors'

type SignInResult = { error: string | null }
type SignUpResult = { error: string | null; needsEmailConfirmation: boolean }

type AuthContextValue = {
  session: Session | null
  user: User | null
  // True until the initial getSession() resolves - RequireAuth (KAN-17) must
  // not redirect to /login on a reload just because the session hasn't been
  // restored from storage yet.
  loading: boolean
  signIn: (email: string, password: string) => Promise<SignInResult>
  signUp: (email: string, password: string) => Promise<SignUpResult>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })

    // Keeps session in sync after the initial load: sign-in/out from this tab,
    // and Supabase's own background access-token refresh (TOKEN_REFRESHED) -
    // the latter is what KAN-19's useWebSocket re-authenticates on.
    const { data: listener } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession)
    })

    return () => listener.subscription.unsubscribe()
  }, [])

  const signIn = async (email: string, password: string): Promise<SignInResult> => {
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    return { error: error ? describeAuthError(error) : null }
  }

  const signUp = async (email: string, password: string): Promise<SignUpResult> => {
    const { data, error } = await supabase.auth.signUp({ email, password })
    return {
      error: error ? describeAuthError(error) : null,
      // signUp() succeeds with data.session === null when email confirmation
      // is required (the dashboard toggle KAN-15's Jira card notes) - the
      // form needs to tell those two successful outcomes apart.
      needsEmailConfirmation: !error && data.session === null,
    }
  }

  const signOut = async (): Promise<void> => {
    await supabase.auth.signOut()
  }

  return (
    <AuthContext.Provider
      value={{ session, user: session?.user ?? null, loading, signIn, signUp, signOut }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}
