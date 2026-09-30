import { useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { SharePanel } from '../components/SharePanel'
import { TranscriptRow } from '../components/TranscriptRow'
import { useAuth } from '../hooks/useAuth'
import { useWebSocket } from '../hooks/useWebSocket'
import { useMicrophone } from '../hooks/useMicrophone'
import { getChunkDurationMs } from '../lib/api'
import { describeConnectionStatus } from '../lib/auth'
import { canChangeSourceLanguage, SUPPORTED_LANGUAGES } from '../lib/languageControls'
import { recordButtonLabel } from '../lib/recording'
import type { LogMessage } from '../lib/types'

function describeMessage(message: LogMessage): string {
  return message.type === 'echo' ? message.text : message.message
}

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
      <div className="mx-auto max-w-2xl px-4 py-8">
        <p>Session not found.</p>
        <Link to="/" className="text-accent-500 hover:text-accent-600">
          Back home
        </Link>
      </div>
    )
  }

  const isRecording = micStatus === 'recording'

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="text-2xl font-semibold text-ink-900">{title ?? 'Untitled session'}</h1>
      <p className="mt-1 text-sm text-ink-500">
        WebSocket status: {describeConnectionStatus(status, isAuthenticated)}
      </p>

      <div className="my-4 flex flex-wrap items-center gap-3">
        <p className="flex items-center gap-2 text-sm text-ink-500">
          Microphone status: {micStatus}
          {isRecording && (
            <span className="relative flex h-3 w-3" aria-label="Recording" role="status">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-400 opacity-75" />
              <span className="relative inline-flex h-3 w-3 rounded-full bg-accent-500" />
            </span>
          )}
        </p>
        {isRecording ? (
          <button
            onClick={handlePause}
            className="rounded bg-accent-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-600"
          >
            {recordButtonLabel(micStatus, hasRecorded)}
          </button>
        ) : (
          <button
            onClick={handleStartRecording}
            disabled={joinStatus !== 'joined' || isStartingRecording}
            className="rounded bg-accent-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {recordButtonLabel(micStatus, hasRecorded)}
          </button>
        )}
        <button
          onClick={handleEndSession}
          className="rounded border border-ink-200 px-3 py-1.5 text-sm font-medium text-ink-900 hover:border-ink-300"
        >
          End session
        </button>
      </div>

      {shareToken && <SharePanel shareToken={shareToken} />}

      <div className="my-4 flex flex-wrap gap-6">
        <label className="flex flex-col gap-1 text-sm text-ink-900">
          Source language
          <select
            value={sourceLanguage ?? 'auto'}
            disabled={!canChangeSourceLanguage(micStatus) || isStartingRecording}
            onChange={(event) =>
              setSourceLanguage(event.target.value === 'auto' ? null : event.target.value)
            }
            className="rounded border border-ink-200 px-2 py-1 text-sm disabled:cursor-not-allowed disabled:opacity-50"
          >
            <option value="auto">Auto-detect</option>
            {SUPPORTED_LANGUAGES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
          {(!canChangeSourceLanguage(micStatus) || isStartingRecording) && (
            <span className="text-xs text-ink-500">Stop recording to change input language</span>
          )}
        </label>

        <label className="flex flex-col gap-1 text-sm text-ink-900">
          Target language
          <select
            value={targetLanguage}
            disabled={joinStatus !== 'joined'}
            onChange={(event) => setTargetLanguage(event.target.value)}
            className="rounded border border-ink-200 px-2 py-1 text-sm disabled:cursor-not-allowed disabled:opacity-50"
          >
            {SUPPORTED_LANGUAGES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="my-4 flex flex-col gap-3">
        {transcriptRows.map((row, index) => (
          <TranscriptRow key={index} row={row} sourceLanguage={sourceLanguage} />
        ))}
        {partialTranscript && (
          <p className="rounded-lg border border-dashed border-ink-200 p-3 text-sm italic text-ink-500">
            {partialTranscript}
          </p>
        )}
      </div>

      <ul className="list-none p-0">
        {messages.map((message, index) => (
          <li key={index} className={message.type === 'error' ? 'text-red-600' : undefined}>
            {describeMessage(message)}
          </li>
        ))}
      </ul>
    </div>
  )
}
