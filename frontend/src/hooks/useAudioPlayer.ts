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
    audio.onended = () => setPlayingUrl((current) => (current === url ? null : current))
    audioRef.current = audio
    setPlayingUrl(url)
    void audio.play()
  }, [])

  const stop = useCallback(() => {
    audioRef.current?.pause()
    setPlayingUrl(null)
  }, [])

  return { playingUrl, play, stop }
}
