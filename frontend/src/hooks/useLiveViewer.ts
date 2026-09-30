import { useCallback, useEffect, useRef, useState } from 'react'
import { getViewerWebSocketUrl } from '../lib/api'
import { DEFAULT_TARGET_LANGUAGE } from '../lib/languageControls'
import type { LiveLineData, LiveState, ViewerServerMessage } from '../lib/types'

export type ViewerJoinStatus = 'joining' | 'joined' | 'not_found'

// Matches backend/routers/viewer_ws.py's LIVE_NOT_AVAILABLE_CLOSE_CODE.
const LIVE_NOT_AVAILABLE_CLOSE_CODE = 4404

// The anonymous counterpart to useWebSocket (KAN-19/KAN-38) - connects to
// /ws/view instead of /ws, sends join_live as its first message instead of
// authenticate/join_session, and never touches Supabase auth: the
// share_token in the URL is this page's only credential (see
// docs/decisions.md D2/D3).
export function useLiveViewer(shareToken: string) {
  const socketRef = useRef<WebSocket | null>(null)
  const [joinStatus, setJoinStatus] = useState<ViewerJoinStatus>('joining')
  const [title, setTitle] = useState<string | null>(null)
  const [sourceLanguage, setSourceLanguage] = useState<string | null>(null)
  const [state, setState] = useState<LiveState | null>(null)
  const [lines, setLines] = useState<LiveLineData[]>([])
  const [targetLanguage, setTargetLanguageState] = useState(DEFAULT_TARGET_LANGUAGE)
  // Read inside onmessage instead of the "targetLanguage" state closed over
  // at mount, so a live_line for a language just switched away from (a
  // request already in flight when set_viewer_language was sent) gets
  // dropped instead of momentarily appearing under the new selection -
  // mirrors routers/ws.py's own _retranslation_generation guard.
  const targetLanguageRef = useRef(targetLanguage)

  const sendJson = useCallback((payload: unknown) => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) return
    socketRef.current.send(JSON.stringify(payload))
  }, [])

  useEffect(() => {
    const socket = new WebSocket(getViewerWebSocketUrl())
    socketRef.current = socket

    socket.onopen = () => {
      if (socketRef.current !== socket) return
      socket.send(
        JSON.stringify({
          type: 'join_live',
          share_token: shareToken,
          target_language: targetLanguageRef.current,
        }),
      )
    }
    socket.onclose = (event) => {
      if (socketRef.current !== socket) return
      if (event.code === LIVE_NOT_AVAILABLE_CLOSE_CODE) setJoinStatus('not_found')
    }
    socket.onmessage = (event) => {
      if (socketRef.current !== socket) return
      const data = JSON.parse(event.data) as ViewerServerMessage

      if (data.type === 'live_joined') {
        setTitle(data.title)
        setSourceLanguage(data.source_language)
        setState(data.state)
        setLines(data.lines)
        setJoinStatus('joined')
        return
      }
      if (data.type === 'live_line') {
        if (data.target_language !== targetLanguageRef.current) return
        setLines((prev) => [...prev, data])
        return
      }
      if (data.type === 'live_lines_retranslated') {
        setLines(data.lines)
        return
      }
      if (data.type === 'live_status') {
        setState(data.state)
        return
      }
      // audio_ready/audio_failed (KAN-58) and error are not handled by this
      // page yet - nothing to render for them until TTS lands.
    }

    return () => socket.close()
    // Mount-once, same reasoning as useWebSocket: this hook is remounted via
    // key={shareToken} by its page, not by re-running this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const setTargetLanguage = useCallback(
    (language: string) => {
      targetLanguageRef.current = language
      setTargetLanguageState(language)
      sendJson({ type: 'set_viewer_language', target_language: language })
    },
    [sendJson],
  )

  return {
    joinStatus,
    title,
    sourceLanguage,
    state,
    lines,
    targetLanguage,
    setTargetLanguage,
  }
}
