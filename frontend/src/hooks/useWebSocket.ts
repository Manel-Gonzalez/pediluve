import { useCallback, useEffect, useRef, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { getWebSocketUrl } from '../lib/api'
import { buildAuthenticateMessage, type ConnectionStatus } from '../lib/auth'
import { buildSetTargetLanguageMessage, buildStartTranscriptionMessage } from '../lib/languageControls'
import type { LogMessage, ServerMessage, TranscriptMessage } from '../lib/types'

// Requires a real session (not Session | null): RequireAuth guarantees one
// before this hook is ever called (see pages/RecordPage.tsx).
export function useWebSocket(session: Session) {
  const socketRef = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [messages, setMessages] = useState<LogMessage[]>([])
  const [partialTranscript, setPartialTranscript] = useState('')
  const [transcriptRows, setTranscriptRows] = useState<TranscriptMessage[]>([])
  const [targetLanguage, setTargetLanguageState] = useState<string | null>(null)

  // A socket that isn't OPEN yet (still connecting) throws on send(); one that's
  // already closing/closed just needs to be skipped. Every outgoing message goes
  // through this guard rather than calling socketRef.current.send() directly.
  const sendJson = useCallback((payload: unknown) => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) return
    socketRef.current.send(JSON.stringify(payload))
  }, [])

  useEffect(() => {
    const socket = new WebSocket(getWebSocketUrl())
    socketRef.current = socket

    socket.onopen = () => {
      if (socketRef.current !== socket) return
      setStatus('open')
      // The connection is otherwise rejected: /ws requires "authenticate" as
      // the first message (backend/routers/ws.py).
      sendJson(buildAuthenticateMessage(session.access_token))
    }
    socket.onclose = () => {
      if (socketRef.current !== socket) return
      setStatus('closed')
      setIsAuthenticated(false)
    }
    socket.onmessage = (event) => {
      if (socketRef.current !== socket) return
      const data = JSON.parse(event.data) as ServerMessage

      if (data.type === 'authenticated') {
        setIsAuthenticated(true)
        return
      }
      if (data.type === 'partial_transcript') {
        setPartialTranscript(data.text)
        return
      }
      if (data.type === 'transcript') {
        setTranscriptRows((prev) => [...prev, data])
        setPartialTranscript('')
        return
      }
      setMessages((prev) => [...prev, data])
    }

    return () => socket.close()
    // Deliberately mount-once (not keyed on session): a later token refresh
    // re-authenticates the same connection below instead of reconnecting it,
    // and RequireAuth guarantees this hook is only ever mounted with a
    // session in the first place.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Supabase refreshes the access token in the background (TOKEN_REFRESHED);
  // re-send "authenticate" on the connection already open above with the new
  // token instead of reconnecting - the backend supports re-authenticating as
  // the same user precisely for this (routers/ws.py::_authenticate). A no-op
  // until the socket actually opens (sendJson's guard), since the initial
  // authenticate above already covers that case.
  useEffect(() => {
    sendJson(buildAuthenticateMessage(session.access_token))
  }, [session.access_token, sendJson])

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
    isAuthenticated,
    messages,
    partialTranscript,
    transcriptRows,
    targetLanguage,
    sendMessage,
    sendAudioChunk,
    startTranscription,
    stopTranscription,
    setTargetLanguage,
  }
}
