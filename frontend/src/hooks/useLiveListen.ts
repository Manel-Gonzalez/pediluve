import { useCallback, useEffect, useRef, useState } from 'react'
import { newLinesToRead } from '../lib/liveTranscript'
import type { LiveLineData } from '../lib/types'

type Options = {
  lines: LiveLineData[]
  audioUrls: Record<number, string>
  audioErrors: Record<number, string>
  requestAudio: (index: number) => void
  play: (url: string, onDone?: () => void) => void
  stop: () => void
  unlock: () => void
}

// "Listen live" on the anonymous viewer page: once started, every line
// that arrives *after* that moment is spoken in order, one at a time -
// request_audio, wait for audio_ready, play, then the next. Starting from
// the next line rather than the backlog is deliberate: reading out
// everything said so far would leave the listener permanently behind.
export function useLiveListen({ lines, audioUrls, audioErrors, requestAudio, play, stop, unlock }: Options) {
  const [listening, setListening] = useState(false)
  const [queue, setQueue] = useState<number[]>([])
  // The line being spoken, or waiting on its audio_ready - null when idle.
  const [currentIndex, setCurrentIndex] = useState<number | null>(null)
  const lastQueuedRef = useRef(-1)
  // Guards against playing the same line twice when audioUrls changes
  // again (another line's audio arriving) while this one is playing.
  const startedRef = useRef(false)

  useEffect(() => {
    if (!listening) return
    const { indexes, lastIndex } = newLinesToRead(lines, lastQueuedRef.current)
    lastQueuedRef.current = lastIndex
    if (!indexes.length) return
    // Requested as soon as queued, not when its turn comes: the next
    // line's audio is generated while the current one is still playing,
    // instead of a 1-2s silence between lines. Same cost either way -
    // every queued line gets spoken.
    indexes.forEach((index) => requestAudio(index))
    setQueue((prev) => [...prev, ...indexes])
  }, [listening, lines, requestAudio])

  useEffect(() => {
    if (!listening || currentIndex !== null || queue.length === 0) return
    const [next, ...rest] = queue
    setQueue(rest)
    startedRef.current = false
    setCurrentIndex(next)
  }, [listening, currentIndex, queue])

  useEffect(() => {
    if (currentIndex === null || startedRef.current) return
    const url = audioUrls[currentIndex]
    if (url) {
      startedRef.current = true
      play(url, () => setCurrentIndex(null))
    } else if (audioErrors[currentIndex]) {
      // Nothing to play for this line - move on rather than stall.
      setCurrentIndex(null)
    }
  }, [currentIndex, audioUrls, audioErrors, play])

  // Must run inside the tap itself: unlock() is what lets every later
  // play() - none of them in a gesture - work on iOS.
  const start = useCallback(() => {
    unlock()
    lastQueuedRef.current = lines.reduce((max, line) => Math.max(max, line.index), -1)
    setQueue([])
    setCurrentIndex(null)
    setListening(true)
  }, [lines, unlock])

  const stopListening = useCallback(() => {
    setListening(false)
    setQueue([])
    setCurrentIndex(null)
    stop()
  }, [stop])

  // A language switch: whatever was queued (or playing) is in the old
  // language, so drop it and carry on from the next new line.
  const resetQueue = useCallback(() => {
    setQueue([])
    setCurrentIndex(null)
    stop()
  }, [stop])

  return { listening, currentIndex, start, stopListening, resetQueue }
}
