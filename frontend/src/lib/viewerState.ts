import type { LiveState } from './types'

export type ViewerJoinStatus = 'joining' | 'joined' | 'not_found'

type Waiting = 'none' | 'not_started' | 'paused'

export type ViewerControls = {
  // The blur over the transcript while waiting (KAN-80)...
  overlay: Waiting
  // ...or, once the viewer closed it, a slim bar under the header instead
  // (KAN-84) - so a paused session's lines can still be read and played.
  statusBar: Waiting
  showEndedNotice: boolean
  showSpeaking: boolean
  languageLocked: boolean
  listenAvailable: boolean
  perLinePlay: 'all' | 'cached_only'
}

export function viewerControls({
  joinStatus,
  state,
  speaking,
  seenRecording,
  linesCount,
  overlayDismissed,
}: {
  joinStatus: ViewerJoinStatus
  state: LiveState | null
  speaking: boolean
  seenRecording: boolean
  linesCount: number
  overlayDismissed: boolean
}): ViewerControls {
  const joined = joinStatus === 'joined'
  const ended = joined && state === 'ended'
  // A room reports "paused" before its first recording too - lines from an
  // earlier visit mean it has recorded before.
  let waiting: Waiting = 'none'
  if (joined && state === 'paused') waiting = seenRecording || linesCount > 0 ? 'paused' : 'not_started'
  return {
    overlay: overlayDismissed ? 'none' : waiting,
    statusBar: overlayDismissed ? waiting : 'none',
    showEndedNotice: ended,
    showSpeaking: joined && state === 'recording' && speaking,
    languageLocked: !joined || ended,
    listenAvailable: joined && !ended,
    perLinePlay: ended ? 'cached_only' : 'all',
  }
}

export type RecordingNotice = 'started' | 'resumed'

// The brief "recording started/resumed" toast (KAN-84): only for a pause
// the viewer actually sat through, not for arriving mid-recording.
export function recordingNotice({
  previous,
  next,
  recordedBefore,
}: {
  previous: LiveState | null
  next: LiveState | null
  recordedBefore: boolean
}): RecordingNotice | null {
  if (previous !== 'paused' || next !== 'recording') return null
  return recordedBefore ? 'resumed' : 'started'
}
