import { useCallback, useEffect, useRef, useState } from 'react'
import { audioToRequest, listenStartAfter, newLinesToRead } from '../lib/liveTranscript'
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
// the next line rather than the backlog is the default: reading out
// everything said so far would leave the listener behind live. "Listen
// from here" (KAN-85) is the opt-in exception - start(index) reads from
// that line on, then carries on live the same way.
export function useLiveListen({ lines, audioUrls, audioErrors, requestAudio, play, stop, unlock }: Options) {
  const [listening, setListening] = useState(false)
  const [queue, setQueue] = useState<number[]>([])
  // The line being spoken, or waiting on its audio_ready - null when idle.
  const [currentIndex, setCurrentIndex] = useState<number | null>(null)
  const lastQueuedRef = useRef(-1)
  // Guards against playing the same line twice when audioUrls changes
  // again (another line's audio arriving) while this one is playing.
  const startedRef = useRef(false)
  // Set by finishAndStop: switch off once the line playing now is done.
  const stopAfterCurrentRef = useRef(false)
  // Lines whose audio this listen already asked for - requestAudio itself
  // doesn't dedupe, and each request can be a paid TTS call.
  const requestedRef = useRef(new Set<number>())

  useEffect(() => {
    if (!listening) return
    const { indexes, lastIndex } = newLinesToRead(lines, lastQueuedRef.current)
    lastQueuedRef.current = lastIndex
    if (!indexes.length) return
    setQueue((prev) => [...prev, ...indexes])
  }, [listening, lines])

  // Audio is requested a couple of lines ahead of its turn, so the next
  // line is ready while the current one still plays (no 1-2s silence in
  // between) - but only a couple: see audioToRequest.
  useEffect(() => {
    if (!listening) return
    const known = new Set([...requestedRef.current, ...Object.keys(audioUrls).map(Number)])
    for (const index of audioToRequest({ current: currentIndex, queue, known })) {
      requestedRef.current.add(index)
      requestAudio(index)
    }
  }, [listening, currentIndex, queue, audioUrls, requestAudio])

  useEffect(() => {
    if (listening && currentIndex === null && stopAfterCurrentRef.current) {
      stopAfterCurrentRef.current = false
      setListening(false)
      return
    }
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
  const start = useCallback(
    (fromIndex?: number) => {
      unlock()
      stopAfterCurrentRef.current = false
      requestedRef.current.clear()
      lastQueuedRef.current = listenStartAfter(lines, fromIndex)
      stop()
      setQueue([])
      setCurrentIndex(null)
      setListening(true)
    },
    [lines, unlock, stop],
  )

  const stopListening = useCallback(() => {
    setListening(false)
    setQueue([])
    setCurrentIndex(null)
    stop()
  }, [stop])

  // A language switch: whatever was queued (or playing) is in the old
  // language, so drop it and carry on from the next new line.
  const resetQueue = useCallback(() => {
    requestedRef.current.clear()
    setQueue([])
    setCurrentIndex(null)
    stop()
  }, [stop])

  // The session ended (KAN-80): no new lines will come, and audio not
  // fetched yet never will - let the line playing now finish, then stop.
  // Nothing playing yet (still waiting on audio) means stop right away.
  const finishAndStop = useCallback(() => {
    setQueue([])
    if (currentIndex !== null && startedRef.current) {
      stopAfterCurrentRef.current = true
      return
    }
    setCurrentIndex(null)
    setListening(false)
  }, [currentIndex])

  return { listening, currentIndex, start, stopListening, resetQueue, finishAndStop }
}
