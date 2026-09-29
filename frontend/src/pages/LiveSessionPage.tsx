import { useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { useWebSocket } from '../hooks/useWebSocket'
import { useMicrophone } from '../hooks/useMicrophone'
import { getChunkDurationMs } from '../lib/api'
import { describeConnectionStatus } from '../lib/auth'
import { canChangeSourceLanguage, SUPPORTED_LANGUAGES } from '../lib/languageControls'
import { recordButtonLabel } from '../lib/recording'
import { describeTranslation, isTranslationPending } from '../lib/transcript'
import type { LogMessage } from '../lib/types'
import './LiveSessionPage.css'

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
      <div className="app">
        <p>Session not found.</p>
        <Link to="/">Back home</Link>
      </div>
    )
  }

  return (
    <div className="app">
      <h1>{title ?? 'Untitled session'}</h1>
      <p>WebSocket status: {describeConnectionStatus(status, isAuthenticated)}</p>

      <div className="mic">
        <p>Microphone status: {micStatus}</p>
        {micStatus === 'recording' ? (
          <button onClick={handlePause}>{recordButtonLabel(micStatus, hasRecorded)}</button>
        ) : (
          <button
            onClick={handleStartRecording}
            disabled={joinStatus !== 'joined' || isStartingRecording}
          >
            {recordButtonLabel(micStatus, hasRecorded)}
          </button>
        )}
        <button onClick={handleEndSession}>End session</button>
      </div>

      <div className="language-controls">
        <label>
          Source language
          <select
            value={sourceLanguage ?? 'auto'}
            disabled={!canChangeSourceLanguage(micStatus) || isStartingRecording}
            onChange={(event) =>
              setSourceLanguage(event.target.value === 'auto' ? null : event.target.value)
            }
          >
            <option value="auto">Auto-detect</option>
            {SUPPORTED_LANGUAGES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
          {(!canChangeSourceLanguage(micStatus) || isStartingRecording) && (
            <span className="hint">Stop recording to change input language</span>
          )}
        </label>

        <label>
          Target language
          <select
            value={targetLanguage}
            disabled={joinStatus !== 'joined'}
            onChange={(event) => setTargetLanguage(event.target.value)}
          >
            {SUPPORTED_LANGUAGES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="transcript">
        <div className="transcript-header">
          <span>Original</span>
          <span>Translation</span>
        </div>
        {transcriptRows.map((row, index) => (
          <div className="transcript-row" key={index}>
            <p className="original">{row.original_text}</p>
            <p className={isTranslationPending(row) ? 'translated pending' : 'translated'}>
              {describeTranslation(row)}
            </p>
          </div>
        ))}
        {partialTranscript && <p className="partial">{partialTranscript}</p>}
      </div>

      <ul>
        {messages.map((message, index) => (
          <li key={index} className={message.type === 'error' ? 'error' : ''}>
            {describeMessage(message)}
          </li>
        ))}
      </ul>
    </div>
  )
}
