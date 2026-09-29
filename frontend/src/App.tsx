import { useState, type FormEvent } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { useMicrophone } from './hooks/useMicrophone'
import { getChunkDurationMs } from './lib/api'
import { canChangeSourceLanguage, SUPPORTED_LANGUAGES } from './lib/languageControls'
import { describeTranslation, isTranslationPending } from './lib/transcript'
import type { LogMessage } from './lib/types'
import './App.css'

function describeMessage(message: LogMessage): string {
  return message.type === 'echo' ? message.text : message.message
}

function App() {
  const {
    status,
    messages,
    partialTranscript,
    transcriptRows,
    targetLanguage,
    sendMessage,
    sendAudioChunk,
    startTranscription,
    stopTranscription,
    setTargetLanguage,
  } = useWebSocket()
  const { status: micStatus, start, stop } = useMicrophone(sendAudioChunk, getChunkDurationMs())
  const [text, setText] = useState('')
  const [sourceLanguage, setSourceLanguage] = useState<string | null>(null)
  const [isStartingRecording, setIsStartingRecording] = useState(false)

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!text.trim()) return
    sendMessage(text)
    setText('')
  }

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

  return (
    <div className="app">
      <h1>Pédiluve</h1>
      <p>WebSocket status: {status}</p>

      <form onSubmit={handleSubmit}>
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Type something and hit send"
        />
        <button type="submit">Send</button>
      </form>

      <div className="mic">
        <p>Microphone status: {micStatus}</p>
        {micStatus === 'recording' ? (
          <button onClick={handleStopRecording}>Stop recording</button>
        ) : (
          <button onClick={handleStartRecording}>Start recording</button>
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
          <select value={targetLanguage ?? ''} onChange={(event) => setTargetLanguage(event.target.value)}>
            <option value="" disabled>
              Select a language
            </option>
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

export default App
