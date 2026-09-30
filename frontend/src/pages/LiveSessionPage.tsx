import { useEffect, useState, type ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, Mic, Pause, Square, X } from 'lucide-react'
import { Button } from '../components/Button'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { IconButton } from '../components/IconButton'
import { SharePanel } from '../components/SharePanel'
import { StatusPill } from '../components/StatusPill'
import { TranscriptRow } from '../components/TranscriptRow'
import { useAuth } from '../hooks/useAuth'
import { useWebSocket } from '../hooks/useWebSocket'
import { useMicrophone } from '../hooks/useMicrophone'
import { getChunkDurationMs } from '../lib/api'
import { canChangeSourceLanguage, SUPPORTED_LANGUAGES } from '../lib/languageControls'
import { languageName } from '../lib/languageLabel'
import { ownerStatus } from '../lib/liveStatus'
import { recordButtonLabel } from '../lib/recording'

export function LiveSessionPage() {
  const { id } = useParams<{ id: string }>()
  const { session } = useAuth()
  // RequireAuth guarantees a session before this page is ever reached; the
  // route always supplies :id. key={id} forces a full remount (fresh
  // useWebSocket, fresh mic state) when navigating between two sessions'
  // live URLs - useWebSocket's connect effect is deliberately mount-once and
  // would otherwise stay joined to the first session.
  if (!session || !id) return null
  return <LiveSessionPageContent key={id} session={session} sessionId={id} />
}

function LiveSessionPageContent({ session, sessionId }: { session: Session; sessionId: string }) {
  const navigate = useNavigate()
  const {
    status,
    isAuthenticated,
    joinStatus,
    title,
    shareToken,
    messages,
    partialTranscript,
    transcriptRows,
    targetLanguage,
    sendAudioChunk,
    startTranscription,
    stopTranscription,
    setTargetLanguage,
  } = useWebSocket(session, sessionId)
  const { status: micStatus, start, stop } = useMicrophone(sendAudioChunk, getChunkDurationMs())
  const [sourceLanguage, setSourceLanguage] = useState<string | null>(null)
  const [isStartingRecording, setIsStartingRecording] = useState(false)
  // Distinct from micStatus: useMicrophone resets to 'idle' on every pause,
  // same as before anything was ever recorded, so the button's own label
  // ("Start" vs "Resume") needs this separate memory - see lib/recording.ts.
  const [hasRecorded, setHasRecorded] = useState(false)
  const [confirmingEnd, setConfirmingEnd] = useState(false)
  // Errors from the socket stay in `messages`; this hides the ones already
  // dismissed from the banner.
  const [dismissedErrors, setDismissedErrors] = useState(0)

  const handleStartRecording = async () => {
    // Disables the source-language control for the whole async gap (mic
    // permission prompt, AudioWorklet setup), not just once micStatus flips to
    // 'recording' - otherwise a language change during that gap would be read
    // here after the fact, out of sync with what the UI showed as selected.
    setIsStartingRecording(true)
    try {
      const sampleRate = await start()
      if (sampleRate !== null) {
        startTranscription(sampleRate, sourceLanguage)
        setHasRecorded(true)
      }
    } finally {
      setIsStartingRecording(false)
    }
  }

  const handlePause = () => {
    stop()
    stopTranscription()
  }

  const handleEndSession = () => {
    stop()
    stopTranscription()
    navigate('/')
  }

  // Signing out (Nav) or any other client-side navigation unmounts this page
  // directly via RequireAuth, not through "End session"/"Pause" above -
  // without this, a recording in progress would keep the microphone and
  // AudioContext live and capturing in the background after the user has
  // already navigated away. Both stop() and stopTranscription() are no-ops
  // when nothing is actually recording, so this is safe to run on every
  // unmount unconditionally.
  useEffect(() => {
    return () => {
      stop()
      stopTranscription()
    }
  }, [stop, stopTranscription])

  // The socket can also close unexpectedly while still recording (a rejected
  // token refresh, a network drop, the backend restarting) - without this,
  // the mic keeps capturing and streaming into a socket that silently drops
  // everything (sendAudioChunk's readyState guard no-ops), with nothing
  // visible beyond the status line changing.
  useEffect(() => {
    if (status === 'closed' && micStatus === 'recording') {
      stop()
    }
  }, [status, micStatus, stop])

  if (joinStatus === 'not_found') {
    return (
      <main className="mx-auto flex max-w-md flex-col items-center px-6 py-24 text-center">
        <h1 className="text-xl font-semibold tracking-tight">Session not found</h1>
        <p className="mt-2 text-sm text-muted">It may have been deleted, or the link is wrong.</p>
        <Link to="/" className="mt-6 text-sm font-medium text-primary hover:text-primary-hover">
          Back to your sessions
        </Link>
      </main>
    )
  }

  const isRecording = micStatus === 'recording'
  const liveStatus = ownerStatus({ status, isAuthenticated, joinStatus, micStatus, hasRecorded })
  const errors = messages.filter((message) => message.type === 'error')
  const visibleErrors = errors.slice(dismissedErrors)
  const sourceLocked = !canChangeSourceLanguage(micStatus) || isStartingRecording

  const languageControls = (
    <div className="flex flex-col gap-4">
      <label className="flex flex-col gap-1.5 text-sm font-medium">
        Spoken language
        <select
          value={sourceLanguage ?? 'auto'}
          disabled={sourceLocked}
          onChange={(event) => setSourceLanguage(event.target.value === 'auto' ? null : event.target.value)}
          className="h-9 rounded-lg border border-line px-2 text-sm font-normal disabled:cursor-not-allowed disabled:opacity-50"
        >
          <option value="auto">Auto-detect</option>
          {SUPPORTED_LANGUAGES.map((code) => (
            <option key={code} value={code}>
              {languageName(code)}
            </option>
          ))}
        </select>
        {sourceLocked && <span className="text-xs font-normal text-muted">Pause to change the spoken language.</span>}
      </label>
      <label className="flex flex-col gap-1.5 text-sm font-medium">
        Translate to
        <select
          value={targetLanguage}
          disabled={joinStatus !== 'joined'}
          onChange={(event) => setTargetLanguage(event.target.value)}
          className="h-9 rounded-lg border border-line px-2 text-sm font-normal disabled:cursor-not-allowed disabled:opacity-50"
        >
          {SUPPORTED_LANGUAGES.map((code) => (
            <option key={code} value={code}>
              {languageName(code)}
            </option>
          ))}
        </select>
      </label>
    </div>
  )

  const recordButton = isRecording ? (
    <Button onClick={handlePause} icon={<Pause className="h-4 w-4" aria-hidden />} className="h-11 flex-1 lg:w-full lg:flex-none">
      {recordButtonLabel(micStatus, hasRecorded)}
    </Button>
  ) : (
    <Button
      variant="primary"
      onClick={handleStartRecording}
      disabled={joinStatus !== 'joined'}
      loading={isStartingRecording}
      icon={<Mic className="h-4 w-4" aria-hidden />}
      className="h-11 flex-1 lg:w-full lg:flex-none"
    >
      {recordButtonLabel(micStatus, hasRecorded)}
    </Button>
  )
  const endButton = (
    <Button
      onClick={() => setConfirmingEnd(true)}
      icon={<Square className="h-3.5 w-3.5" aria-hidden />}
      className="h-11 lg:w-full"
    >
      End session
    </Button>
  )

  return (
    <main className="mx-auto max-w-5xl px-4 pb-28 pt-6 sm:px-6 lg:grid lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-8 lg:pb-12">
      <div className="min-w-0">
        <Link to="/" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-fg">
          <ChevronLeft className="h-4 w-4" aria-hidden />
          Sessions
        </Link>
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <h1 className="min-w-0 truncate text-2xl font-semibold tracking-tight">{title ?? 'Untitled session'}</h1>
          <StatusPill status={liveStatus} />
        </div>

        {visibleErrors.length > 0 && (
          <div role="alert" className="mb-4 flex items-start gap-2 rounded-lg bg-danger-soft py-1 pl-4 pr-1 text-sm text-danger">
            <span className="flex-1 py-2">{visibleErrors[visibleErrors.length - 1].message}</span>
            <IconButton label="Dismiss" onClick={() => setDismissedErrors(errors.length)}>
              <X className="h-4 w-4" aria-hidden />
            </IconButton>
          </div>
        )}

        {/* Languages and sharing sit above the transcript on phones, in the
            side column on desktop. */}
        <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:hidden">
          <Card title="Languages">{languageControls}</Card>
          {shareToken && (
            <Card title="Share live">
              <SharePanel shareToken={shareToken} />
            </Card>
          )}
        </div>

        <section aria-label="Transcript" className="flex flex-col gap-3">
          {transcriptRows.map((row, index) => (
            <TranscriptRow key={index} row={row} sourceLanguage={sourceLanguage} />
          ))}
          {partialTranscript && (
            <p className="rounded-xl border border-dashed border-line px-4 py-3 text-sm italic text-muted">
              {partialTranscript}
            </p>
          )}
          {transcriptRows.length === 0 && !partialTranscript && (
            <div className="rounded-xl border border-dashed border-line px-6 py-12 text-center text-sm text-muted">
              {isRecording
                ? 'Listening… start speaking.'
                : 'Press “Start recording” and speak - your words and their translation appear here.'}
            </div>
          )}
        </section>
      </div>

      <aside className="hidden lg:block">
        <div className="sticky top-20 flex flex-col gap-4">
          <Card title="Recording">
            <div className="flex flex-col gap-2">
              {recordButton}
              {endButton}
            </div>
          </Card>
          <Card title="Languages">{languageControls}</Card>
          {shareToken && (
            <Card title="Share live">
              <SharePanel shareToken={shareToken} />
            </Card>
          )}
        </div>
      </aside>

      {/* Phones: the record controls stay within thumb reach. */}
      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-canvas/90 px-4 py-3 backdrop-blur lg:hidden">
        <div className="mx-auto flex max-w-5xl gap-2">
          {recordButton}
          {endButton}
        </div>
      </div>

      <ConfirmDialog
        open={confirmingEnd}
        onClose={() => setConfirmingEnd(false)}
        title="End this session?"
        description="Recording stops, and everyone following the live link will see that the session has ended. The transcript stays in your sessions."
        confirmLabel="End session"
        onConfirm={async () => handleEndSession()}
      />
    </main>
  )
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-surface p-4">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">{title}</h2>
      {children}
    </section>
  )
}
