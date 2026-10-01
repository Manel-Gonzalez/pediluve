import type { LiveLineData } from './types'

// Client-side download for the anonymous live viewer (KAN-50 follow-up):
// unlike SessionDetailPage (which fetches GET /api/sessions/{id}/transcript),
// this page has no Supabase session to authenticate a REST call with - but
// it already holds every line in state via useLiveViewer, so building the
// file client-side needs no backend endpoint at all. Translation-only,
// matching what the viewer page itself shows (the original text isn't
// rendered there either - see ViewLiveSessionPage.tsx).
export function buildLiveTranscriptText(lines: LiveLineData[]): string {
  const translated = lines.map((line) => line.translated_text).filter((text): text is string => !!text)
  return translated.length ? `${translated.join('\n\n')}\n` : ''
}

// "Listen live" (useLiveListen): which lines arrived since the last one
// queued. A line with no translation (its DeepL call failed) has nothing
// to speak, but still counts as seen so it's never picked up later.
// lastIndex is where the next call picks up from.
export function newLinesToRead(
  lines: LiveLineData[],
  lastQueuedIndex: number,
): { indexes: number[]; lastIndex: number } {
  let lastIndex = lastQueuedIndex
  const indexes: number[] = []
  for (const line of lines) {
    if (line.index <= lastQueuedIndex) continue
    lastIndex = Math.max(lastIndex, line.index)
    if (line.translated_text) indexes.push(line.index)
  }
  return { indexes, lastIndex }
}

// Where Listen live's queue starts (KAN-85): after the latest line, so only
// lines said from now on are read - or, for "Listen from here", just before
// the line the listener picked, so it and everything after it are read.
export function listenStartAfter(lines: LiveLineData[], fromIndex?: number): number {
  if (fromIndex !== undefined) return fromIndex - 1
  return lines.reduce((max, line) => Math.max(max, line.index), -1)
}

// How many queued lines get their audio generated ahead of their turn.
export const PREFETCH_AHEAD = 2

// Which lines' audio to request now: the one playing plus the next few,
// not the whole queue. A catch-up from line 1 of a long session would
// otherwise fire dozens of paid TTS calls at once, most of them wasted if
// the listener stops early. `known` holds lines already requested or with
// audio in hand.
export function audioToRequest({
  current,
  queue,
  known,
  ahead = PREFETCH_AHEAD,
}: {
  current: number | null
  queue: number[]
  known: ReadonlySet<number>
  ahead?: number
}): number[] {
  const window = current === null ? queue.slice(0, ahead) : [current, ...queue.slice(0, ahead)]
  return window.filter((index) => !known.has(index))
}
