export type ClientMessage = {
  type: 'message'
  text: string
}

export type EchoMessage = {
  type: 'echo'
  text: string
}

export type ErrorMessage = {
  type: 'error'
  message: string
}

export type PartialTranscriptMessage = {
  type: 'partial_transcript'
  text: string
}

export type TranscriptMessage = {
  type: 'transcript'
  original_text: string
  translated_text: string | null
  target_language: string | null
}

export type StartTranscriptionMessage = {
  type: 'start_transcription'
  audio_format: string
  source_language?: string
}

export type SetTargetLanguageMessage = {
  type: 'set_target_language'
  target_language: string
}

export type AuthenticateMessage = {
  type: 'authenticate'
  access_token: string
}

export type AuthenticatedMessage = {
  type: 'authenticated'
  user_id: string
}

// Attaches this WS connection to an already-created session (created via the
// REST API's POST /api/sessions, KAN-24) instead of the connection implicitly
// creating one.
export type JoinSessionMessage = {
  type: 'join_session'
  session_id: string
}

// Reply to a successful join_session: the session's current metadata plus
// every transcript already stored, so the live view can render history
// before anything new is said.
export type SessionJoinedMessage = {
  type: 'session_joined'
  session_id: string
  title: string | null
  source_language: string | null
  target_language: string | null
  transcripts: TranscriptMessage[]
  // The capability token for this session's QR/share link (KAN-50).
  share_token: string
}

// Sent when the target language changes mid-session and there's already
// committed transcript to retranslate - replaces the whole transcript list
// rather than patching individual rows (no per-message id goes over the
// wire for that).
export type RetranslatedTranscriptsMessage = {
  type: 'retranslated_transcripts'
  target_language: string
  transcripts: TranscriptMessage[]
}

export type LogMessage = EchoMessage | ErrorMessage

export type ServerMessage =
  | LogMessage
  | PartialTranscriptMessage
  | TranscriptMessage
  | AuthenticatedMessage
  | SessionJoinedMessage
  | RetranslatedTranscriptsMessage

// ── REST session models (KAN-23), matching backend/models/sessions.py ─────
// Note: unrelated to @supabase/supabase-js's Session (the auth session) used
// throughout useAuth/useWebSocket - this "session" is a recording/transcript
// session, the thing the home page lists.

export type SessionSummary = {
  id: string
  created_at: string
  ended_at: string | null
  source_language: string | null
  target_language: string | null
  title: string | null
  message_count: number
}

export type SessionListResponse = {
  items: SessionSummary[]
  has_more: boolean
}

export type MessageRecord = {
  id: string
  sequence: number
  created_at: string
  original_text: string
  translated_text: string | null
  target_language: string | null
}

export type SessionDetail = SessionSummary & {
  messages: MessageRecord[]
}

export type MessageTranslation = {
  message_id: string
  translated_text: string | null
}

export type TranslateResponse = {
  target_language: string
  translations: MessageTranslation[]
}

// ── /ws/view viewer models (KAN-50/KAN-56), matching backend/models/viewer.py

export type LiveState = 'recording' | 'paused' | 'ended'

export type LiveLineData = {
  index: number
  original_text: string
  translated_text: string | null
}

export type JoinLiveMessage = {
  type: 'join_live'
  share_token: string
  target_language: string
}

export type SetViewerLanguageMessage = {
  type: 'set_viewer_language'
  target_language: string
}

export type RequestAudioMessage = {
  type: 'request_audio'
  index: number
}

export type LiveJoinedMessage = {
  type: 'live_joined'
  title: string | null
  source_language: string | null
  target_language: string
  state: LiveState
  lines: LiveLineData[]
}

export type LiveLineMessage = {
  type: 'live_line'
  index: number
  original_text: string
  translated_text: string | null
  target_language: string
}

export type LiveLinesRetranslatedMessage = {
  type: 'live_lines_retranslated'
  target_language: string
  lines: LiveLineData[]
}

export type LiveStatusMessage = {
  type: 'live_status'
  state: LiveState
}

export type AudioReadyMessage = {
  type: 'audio_ready'
  index: number
  target_language: string
  audio_url: string
  cached: boolean
}

export type AudioFailedMessage = {
  type: 'audio_failed'
  index: number
  message: string
}

export type ViewerServerMessage =
  | LiveJoinedMessage
  | LiveLineMessage
  | LiveLinesRetranslatedMessage
  | LiveStatusMessage
  | AudioReadyMessage
  | AudioFailedMessage
  | ErrorMessage
