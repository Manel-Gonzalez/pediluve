import { useState, type FormEvent } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import './App.css'

function App() {
  const { status, messages, sendMessage } = useWebSocket()
  const [text, setText] = useState('')

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!text.trim()) return
    sendMessage(text)
    setText('')
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

      <ul>
        {messages.map((message, index) => (
          <li key={index} className={message.type === 'error' ? 'error' : ''}>
            {message.type === 'echo' ? message.text : message.message}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default App
