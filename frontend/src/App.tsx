import { useState, type FormEvent } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { useMicrophone } from './hooks/useMicrophone'
import { getChunkDurationMs } from './lib/api'
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
    transcriptLines,
    sendMessage,
    sendAudioChunk,
    startTranscription,
    stopTranscription,
  } = useWebSocket()
  const { status: micStatus, start, stop } = useMicrophone(sendAudioChunk, getChunkDurationMs())
  const [text, setText] = useState('')

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!text.trim()) return
    sendMessage(text)
    setText('')
  }

  const handleStartRecording = async () => {
    const sampleRate = await start()
    if (sampleRate !== null) startTranscription(sampleRate)
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

      <div className="transcript">
        {transcriptLines.map((line, index) => (
          <p key={index}>{line}</p>
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
