import type { LiveState } from './types'

export type ViewerJoinStatus = 'joining' | 'joined' | 'not_found'

export type ViewerControls = {
  // Blur over the transcript while nothing is being said on purpose.
  overlay: 'none' | 'not_started' | 'paused'
  showEndedNotice: boolean
  showSpeaking: boolean
  languageLocked: boolean
  listenAvailable: boolean
  // After the end the live room is gone: only audio already fetched plays.
  perLinePlay: 'all' | 'cached_only'
}

// What the anonymous viewer page shows for a given live state (KAN-80).
// A room starts "paused" until its owner first presses record, so "paused"
// alone can't tell "not started yet" from "on a break": having seen
// recording, or having lines at all (a resumed session), means the latter.
export function viewerControls({
  joinStatus,
  state,
  speaking,
  seenRecording,
  linesCount,
}: {
  joinStatus: ViewerJoinStatus
  state: LiveState | null
  speaking: boolean
  seenRecording: boolean
  linesCount: number
}): ViewerControls {
  const joined = joinStatus === 'joined'
  const ended = joined && state === 'ended'
  let overlay: ViewerControls['overlay'] = 'none'
  if (joined && state === 'paused') overlay = seenRecording || linesCount > 0 ? 'paused' : 'not_started'
  return {
    overlay,
    showEndedNotice: ended,
    showSpeaking: joined && state === 'recording' && speaking,
    languageLocked: !joined || ended,
    listenAvailable: joined && !ended,
    perLinePlay: ended ? 'cached_only' : 'all',
  }
}
