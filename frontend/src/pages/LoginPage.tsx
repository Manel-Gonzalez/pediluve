import { Navigate, useLocation } from 'react-router-dom'
import { AudioLines, Headphones, Languages, QrCode } from 'lucide-react'
import { AuthForm } from '../components/AuthForm'
import { LogoMark } from '../components/LogoMark'
import { ThemeToggle } from '../components/ThemeToggle'
import { useAuth } from '../hooks/useAuth'
import { postLoginRedirect } from '../lib/routes'

const FEATURES = [
  { icon: AudioLines, title: 'Live transcription', text: 'Your words appear while you speak.' },
  { icon: Languages, title: 'Instant translation', text: 'Every sentence, in the language you choose.' },
  { icon: QrCode, title: 'Share with a QR code', text: 'Listeners follow on their phone - no app, no account.' },
  { icon: Headphones, title: 'Listen along', text: 'Each new line can be read aloud as it arrives.' },
]

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
    <div className="grid min-h-screen lg:grid-cols-2">
      <aside className="relative hidden overflow-hidden border-r border-line bg-subtle lg:flex lg:flex-col lg:justify-between lg:p-12">
        {/* Soft accent glow behind the content. */}
        <div
          aria-hidden
          className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full bg-primary/15 blur-3xl"
        />
        <div className="relative flex items-center gap-2 font-semibold tracking-tight">
          <LogoMark />
          Pédiluve
        </div>

        <div className="relative max-w-md">
          <h2 className="text-3xl font-semibold tracking-tight">
            Speak in one language.
            <br />
            <span className="text-primary">Everyone reads it in theirs.</span>
          </h2>
          <ul className="mt-8 space-y-4">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-3">
                <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface text-primary ring-1 ring-line">
                  <Icon className="h-4 w-4" aria-hidden />
                </span>
                <span>
                  <span className="block text-sm font-medium">{title}</span>
                  <span className="block text-sm text-muted">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <LiveCaptionCard />
      </aside>

      <main className="relative flex flex-col items-center justify-center px-4 py-12 sm:px-6">
        <ThemeToggle className="absolute right-4 top-4" />
        {/* The hero is desktop-only; phones get just the mark and a tagline. */}
        <div className="mb-10 flex flex-col items-center gap-3 text-center lg:hidden">
          <LogoMark className="h-10 w-10" />
          <p className="text-sm text-muted">Speak in one language. Everyone reads it in theirs.</p>
        </div>
        <AuthForm />
      </main>
    </div>
  )
}

// A static-content, CSS-animated preview of what the app does: a waveform
// and caption pairs fading in. Everything moves only under motion-safe.
function LiveCaptionCard() {
  const bars = [0.5, 0.9, 0.6, 1, 0.7, 0.4, 0.8, 0.55, 0.95, 0.65, 0.45, 0.75]
  const captions = [
    { original: 'Bienvenidos a la reunión de hoy.', translated: "Welcome to today's meeting." },
    { original: 'Empezamos con las novedades.', translated: "Let's start with the news." },
  ]
  return (
    <div aria-hidden className="relative max-w-md rounded-2xl border border-line bg-surface p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <span className="flex items-center gap-2 text-xs font-medium text-muted">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full rounded-full bg-accent-400 opacity-75 motion-safe:animate-ping" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
          </span>
          Live · ES → EN
        </span>
        <span className="flex h-6 items-center gap-0.5">
          {bars.map((height, i) => (
            <span
              key={i}
              className="w-1 origin-center rounded-full bg-primary/70 motion-safe:animate-wave"
              style={{ height: `${height * 100}%`, animationDelay: `${i * 90}ms` }}
            />
          ))}
        </span>
      </div>
      <div className="space-y-3">
        {captions.map((caption, i) => (
          <div
            key={caption.original}
            className="motion-safe:animate-caption-in"
            style={{ animationDelay: `${400 + i * 900}ms` }}
          >
            <p className="text-sm text-muted">{caption.original}</p>
            <p className="text-base font-medium">{caption.translated}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
