import { useCallback, useEffect, useRef, useState } from 'react'

// 1ms of silence - played by unlock() purely so the element has been
// play()ed once inside a user gesture (see unlock below).
const SILENT_WAV =
  'data:audio/wav;base64,UklGRjQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YRAAAAAAAAAAAAAAAAAAAAAAAAAA'

// One <audio> element for the page's lifetime, reused for every play - not
// a new one per play. iOS Safari only lets an element play without a
// fresh user gesture once that same element has been played inside one:
// a new element per play meant anything started outside a tap (auto-play
// after audio_ready, "Listen live" reading lines one after another) was
// blocked after the first.
export function useAudioPlayer() {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  // Called once the current play ends or fails - how "Listen live" knows
  // to move on to the next queued line. Cleared by stop()/unlock()/a
  // newer play(), so a replaced track never fires a stale callback.
  const onDoneRef = useRef<(() => void) | null>(null)
  const [playingUrl, setPlayingUrl] = useState<string | null>(null)

  const finish = useCallback(() => {
    const done = onDoneRef.current
    onDoneRef.current = null
    setPlayingUrl(null)
    done?.()
  }, [])

  const getAudio = useCallback(() => {
    if (!audioRef.current) {
      const audio = new Audio()
      // A stale "ended" from a track already replaced (the 1ms unlock clip,
      // right as the first real line starts) must not count as that line
      // finishing - "Listen live" would skip it. Loading a new src resets
      // .ended, so only the track actually playing passes this.
      audio.onended = () => {
        if (audio.ended) finish()
      }
      audioRef.current = audio
    }
    return audioRef.current
  }, [finish])

  useEffect(() => {
    return () => {
      audioRef.current?.pause()
    }
  }, [])

  const play = useCallback(
    (url: string, onDone?: () => void) => {
      const audio = getAudio()
      onDoneRef.current = onDone ?? null
      audio.src = url
      setPlayingUrl(url)
      audio.play().catch((error: unknown) => {
        // A newer play()/unlock() replaced this one before it started -
        // not a failure, and the callback now belongs to the newer one.
        if (error instanceof DOMException && error.name === 'AbortError') return
        // A load failure, or the autoplay policy rejecting it - reset so
        // the button shows "Play" again (a second tap, a real gesture,
        // then works), and let a queue move on rather than stall.
        console.error('Could not play audio:', error)
        finish()
      })
    },
    [getAudio, finish],
  )

  const stop = useCallback(() => {
    audioRef.current?.pause()
    onDoneRef.current = null
    setPlayingUrl(null)
  }, [])

  // Must be called synchronously inside a tap handler, before anything
  // async: plays silence on the shared element so later play() calls made
  // outside a gesture are allowed on iOS.
  const unlock = useCallback(() => {
    const audio = getAudio()
    onDoneRef.current = null
    setPlayingUrl(null)
    audio.src = SILENT_WAV
    audio.play().catch(() => {})
  }, [getAudio])

  return { playingUrl, play, stop, unlock }
}
