import { useCallback, useEffect, useRef, useState } from 'react'
import { getWebSocketUrl } from '../lib/api'
import { buildSetTargetLanguageMessage, buildStartTranscriptionMessage } from '../lib/languageControls'
import type { LogMessage, ServerMessage } from '../lib/types'

type ConnectionStatus = 'connecting' | 'open' | 'closed'

export function useWebSocket() {
  const socketRef = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const [messages, setMessages] = useState<LogMessage[]>([])
  const [partialTranscript, setPartialTranscript] = useState('')
  const [transcriptLines, setTranscriptLines] = useState<string[]>([])
  const [targetLanguage, setTargetLanguageState] = useState<string | null>(null)

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

  // A socket that isn't OPEN yet (still connecting) throws on send(); one that's
  // already closing/closed just needs to be skipped. Every outgoing message goes
  // through this guard rather than calling socketRef.current.send() directly.
  const sendJson = useCallback((payload: unknown) => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) return
    socketRef.current.send(JSON.stringify(payload))
  }, [])

  const sendMessage = useCallback(
    (text: string) => {
      sendJson({ type: 'message', text })
    },
    [sendJson],
  )

  const sendAudioChunk = useCallback((chunk: ArrayBuffer) => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) return
    socketRef.current.send(chunk)
  }, [])

  const startTranscription = useCallback(
    (sampleRate: number, sourceLanguage: string | null) => {
      sendJson(buildStartTranscriptionMessage(`pcm_${sampleRate}`, sourceLanguage))
    },
    [sendJson],
  )

  const stopTranscription = useCallback(() => {
    sendJson({ type: 'stop_transcription' })
  }, [sendJson])

  const setTargetLanguage = useCallback(
    (language: string) => {
      setTargetLanguageState(language)
      sendJson(buildSetTargetLanguageMessage(language))
    },
    [sendJson],
  )

  return {
    status,
    messages,
    partialTranscript,
    transcriptLines,
    targetLanguage,
    sendMessage,
    sendAudioChunk,
    startTranscription,
    stopTranscription,
    setTargetLanguage,
  }
}
