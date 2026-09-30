import { useCallback, useEffect, useRef, useState } from 'react'

// Wraps a single native Audio element so PlayButton can offer real
// play/pause control instead of the browser's default <audio controls>
// widget - one element reused across plays, not recreated on every click.
export function useAudioPlayer() {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [playingUrl, setPlayingUrl] = useState<string | null>(null)

  useEffect(() => {
    return () => {
      audioRef.current?.pause()
    }
  }, [])

  const play = useCallback((url: string) => {
    audioRef.current?.pause()
    const audio = new Audio(url)
    const reset = () => setPlayingUrl((current) => (current === url ? null : current))
    audio.onended = reset
    audioRef.current = audio
    setPlayingUrl(url)
    audio.play().catch((error) => {
      // A load failure, or the browser's autoplay policy rejecting a
      // play() that didn't happen directly inside a tap (see
      // ViewLiveSessionPage's auto-play after audio_ready - strict on iOS
      // Safari) - reset so the button shows "Play" again, and a second
      // tap, which *is* a user gesture, plays it.
      console.error('Could not play audio:', error)
      reset()
    })
  }, [])

  const stop = useCallback(() => {
    audioRef.current?.pause()
    setPlayingUrl(null)
  }, [])

  return { playingUrl, play, stop }
}
