import { useState, type FormEvent } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { useMicrophone } from './hooks/useMicrophone'
import { getChunkDurationMs } from './lib/api'
import type { ServerMessage } from './lib/types'
import './App.css'

function describeMessage(message: ServerMessage): string {
  switch (message.type) {
    case 'echo':
      return message.text
    case 'error':
      return message.message
    case 'partial_transcript':
      return `… ${message.text}`
    case 'transcript':
      return message.text
  }
}

function App() {
  const { status, messages, sendMessage, sendAudioChunk, startTranscription, stopTranscription } =
    useWebSocket()
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
