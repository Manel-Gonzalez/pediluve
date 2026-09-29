import { useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { useAuth } from '../hooks/useAuth'
import { useWebSocket } from '../hooks/useWebSocket'
import { useMicrophone } from '../hooks/useMicrophone'
import { getChunkDurationMs } from '../lib/api'
import { describeConnectionStatus } from '../lib/auth'
import { canChangeSourceLanguage, SUPPORTED_LANGUAGES } from '../lib/languageControls'
import { describeTranslation, isTranslationPending } from '../lib/transcript'
import type { LogMessage } from '../lib/types'
import './RecordPage.css'

function describeMessage(message: LogMessage): string {
  return message.type === 'echo' ? message.text : message.message
}

export function RecordPage() {
  const { session } = useAuth()
  // RequireAuth guarantees a session before this page is ever reached; the
  // split into RecordPageContent keeps useWebSocket (which needs a real
  // session, for the authenticate handshake) from ever being called
  // conditionally.
  if (!session) return null
  return <RecordPageContent session={session} />
}

function RecordPageContent({ session }: { session: Session }) {
  const {
    status,
    isAuthenticated,
    messages,
    partialTranscript,
    transcriptRows,
    targetLanguage,
    sendAudioChunk,
    startTranscription,
    stopTranscription,
    setTargetLanguage,
  } = useWebSocket(session)
  const { status: micStatus, start, stop } = useMicrophone(sendAudioChunk, getChunkDurationMs())
  const [sourceLanguage, setSourceLanguage] = useState<string | null>(null)
  const [isStartingRecording, setIsStartingRecording] = useState(false)

  const handleStartRecording = async () => {
    // Disables the source-language control for the whole async gap (mic
    // permission prompt, AudioWorklet setup), not just once micStatus flips to
    // 'recording' - otherwise a language change during that gap would be read
    // here after the fact, out of sync with what the UI showed as selected.
    setIsStartingRecording(true)
    try {
      const sampleRate = await start()
      if (sampleRate !== null) startTranscription(sampleRate, sourceLanguage)
    } finally {
      setIsStartingRecording(false)
    }
  }

  const handleStopRecording = () => {
    stop()
    stopTranscription()
  }

  // Signing out (Nav) or any other client-side navigation unmounts this page
  // directly via RequireAuth, not through the "Stop recording" button above -
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

  return (
    <div className="app">
      <p>WebSocket status: {describeConnectionStatus(status, isAuthenticated)}</p>

      <div className="mic">
        <p>Microphone status: {micStatus}</p>
        {micStatus === 'recording' ? (
          <button onClick={handleStopRecording}>Stop recording</button>
        ) : (
          <button onClick={handleStartRecording} disabled={!isAuthenticated}>
            Start recording
          </button>
        )}
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
            disabled={!isAuthenticated}
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
