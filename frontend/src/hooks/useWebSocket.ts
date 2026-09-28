import { useCallback, useEffect, useRef, useState } from 'react'
import { getWebSocketUrl } from '../lib/api'
import type { ServerMessage } from '../lib/types'

type ConnectionStatus = 'connecting' | 'open' | 'closed'

export function useWebSocket() {
  const socketRef = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const [messages, setMessages] = useState<ServerMessage[]>([])

  useEffect(() => {
    const socket = new WebSocket(getWebSocketUrl())
    socketRef.current = socket

    socket.onopen = () => setStatus('open')
    socket.onclose = () => setStatus('closed')
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data) as ServerMessage
      setMessages((prev) => [...prev, data])
    }

    return () => socket.close()
  }, [])

  const sendMessage = useCallback((text: string) => {
    socketRef.current?.send(JSON.stringify({ type: 'message', text }))
  }, [])

  return { status, messages, sendMessage }
}
