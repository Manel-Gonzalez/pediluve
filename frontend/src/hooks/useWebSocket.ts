import { useCallback, useEffect, useRef, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { getWebSocketUrl } from '../lib/api'
import { buildAuthenticateMessage, buildJoinSessionMessage, type ConnectionStatus } from '../lib/auth'
import {
  buildSetTargetLanguageMessage,
  buildStartTranscriptionMessage,
  DEFAULT_TARGET_LANGUAGE,
} from '../lib/languageControls'
import type { LogMessage, ServerMessage, TranscriptMessage } from '../lib/types'

export type JoinStatus = 'joining' | 'joined' | 'not_found'

// Matches backend/routers/ws.py's SESSION_NOT_FOUND_CLOSE_CODE.
const SESSION_NOT_FOUND_CLOSE_CODE = 4404

// Requires a real session (not Session | null): RequireAuth guarantees one
// before this hook is ever called (see pages/LiveSessionPage.tsx). sessionId
// is the id join_session attaches to once authenticated.
export function useWebSocket(session: Session, sessionId: string) {
  const socketRef = useRef<WebSocket | null>(null)
  // Always the latest session, read from inside onopen instead of the
  // "session" the connect effect below closed over at mount - see onopen's
  // comment for why the two are not interchangeable.
  const sessionRef = useRef(session)
  sessionRef.current = session
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [joinStatus, setJoinStatus] = useState<JoinStatus>('joining')
  const [title, setTitle] = useState<string | null>(null)
  // The session's QR/share-link token (KAN-50), set once session_joined
  // arrives - consumed by the Share panel (KAN-57).
  const [shareToken, setShareToken] = useState<string | null>(null)
  const [messages, setMessages] = useState<LogMessage[]>([])
  const [partialTranscript, setPartialTranscript] = useState('')
  const [transcriptRows, setTranscriptRows] = useState<TranscriptMessage[]>([])
  // Overwritten by session_joined once it arrives (the session's own stored
  // target language, or this default if it never had one) - this initial
  // value is only ever visible for the brief joining window before that.
  const [targetLanguage, setTargetLanguageState] = useState(DEFAULT_TARGET_LANGUAGE)

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
      // Reads sessionRef, not the "session" this effect closed over at mount:
      // a token refresh landing while the socket was still CONNECTING would
      // otherwise be lost - the effect below only re-sends on a *change* of
      // session.access_token, which may already have fired (as a no-op,
      // socket not OPEN yet) before this handler runs, leaving nothing to
      // trigger a resend once it actually opens. sessionRef.current is always
      // the token from the most recent render, so this always authenticates
      // with whatever's current the moment the handshake actually happens.
      sendJson(buildAuthenticateMessage(sessionRef.current.access_token))
    }
    socket.onclose = (event) => {
      if (socketRef.current !== socket) return
      setStatus('closed')
      setIsAuthenticated(false)
      if (event.code === SESSION_NOT_FOUND_CLOSE_CODE) setJoinStatus('not_found')
    }
    socket.onmessage = (event) => {
      if (socketRef.current !== socket) return
      const data = JSON.parse(event.data) as ServerMessage

      if (data.type === 'authenticated') {
        setIsAuthenticated(true)
        // sessionId, not a value read off props again: this effect is
        // mount-once (see below) and LiveSessionPage remounts this whole
        // hook with key={id} on navigating to a different session, so the
        // sessionId captured here at mount never goes stale.
        sendJson(buildJoinSessionMessage(sessionId))
        return
      }
      if (data.type === 'session_joined') {
        setTitle(data.title)
        setShareToken(data.share_token)
        setTranscriptRows(data.transcripts)
        // Replaces the old "send DEFAULT_TARGET_LANGUAGE once authenticated"
        // behavior: a session already has its own target_language (null for
        // one that's never had a language chosen), and that's now the
        // starting point instead of always defaulting.
        const language = data.target_language ?? DEFAULT_TARGET_LANGUAGE
        setTargetLanguageState(language)
        sendJson(buildSetTargetLanguageMessage(language))
        setJoinStatus('joined')
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
      if (data.type === 'retranslated_transcripts') {
        setTranscriptRows(data.transcripts)
        return
      }
      setMessages((prev) => [...prev, data])
    }

    return () => socket.close()
    // Deliberately mount-once (not keyed on session or sessionId): a later
    // token refresh re-authenticates the same connection below instead of
    // reconnecting it, RequireAuth guarantees this hook is only ever mounted
    // with a session in the first place, and sessionId never changes without
    // a remount (LiveSessionPage's key={id}).
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
    joinStatus,
    title,
    shareToken,
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
