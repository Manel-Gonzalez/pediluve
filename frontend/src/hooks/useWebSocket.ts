import { useCallback, useEffect, useRef, useState } from 'react'
import { getWebSocketUrl } from '../lib/api'
import type { LogMessage, ServerMessage } from '../lib/types'

type ConnectionStatus = 'connecting' | 'open' | 'closed'

export function useWebSocket() {
  const socketRef = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const [messages, setMessages] = useState<LogMessage[]>([])
  const [partialTranscript, setPartialTranscript] = useState('')
  const [transcriptLines, setTranscriptLines] = useState<string[]>([])

  useEffect(() => {
    const socket = new WebSocket(getWebSocketUrl())
    socketRef.current = socket

    socket.onopen = () => {
      if (socketRef.current === socket) setStatus('open')
    }
    socket.onclose = () => {
      if (socketRef.current === socket) setStatus('closed')
    }
    socket.onmessage = (event) => {
      if (socketRef.current !== socket) return
      const data = JSON.parse(event.data) as ServerMessage

      if (data.type === 'partial_transcript') {
        setPartialTranscript(data.text)
        return
      }
      if (data.type === 'transcript') {
        setTranscriptLines((prev) => [...prev, data.text])
        setPartialTranscript('')
        return
      }
      setMessages((prev) => [...prev, data])
    }

    return () => socket.close()
  }, [])

  const sendMessage = useCallback((text: string) => {
    socketRef.current?.send(JSON.stringify({ type: 'message', text }))
  }, [])

  const sendAudioChunk = useCallback((chunk: ArrayBuffer) => {
    socketRef.current?.send(chunk)
  }, [])

  const startTranscription = useCallback((sampleRate: number) => {
    socketRef.current?.send(
      JSON.stringify({ type: 'start_transcription', audio_format: `pcm_${sampleRate}` }),
    )
  }, [])

  const stopTranscription = useCallback(() => {
    socketRef.current?.send(JSON.stringify({ type: 'stop_transcription' }))
  }, [])

  return {
    status,
    messages,
    partialTranscript,
    transcriptLines,
    sendMessage,
    sendAudioChunk,
    startTranscription,
    stopTranscription,
  }
}
