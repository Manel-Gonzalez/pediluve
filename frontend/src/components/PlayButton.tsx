import { useAudioPlayer } from '../hooks/useAudioPlayer'

// Per-line playback (KAN-33/KAN-58): first click requests the audio (a
// cache miss costs one ElevenLabs call server-side, a hit is instant), a
// later click just replays the signed URL already held.
export function PlayButton({
  index,
  audioUrl,
  loading,
  error,
  onRequestAudio,
}: {
  index: number
  audioUrl: string | null
  loading: boolean
  error: string | null
  onRequestAudio: (index: number) => void
}) {
  const { playingUrl, play, stop } = useAudioPlayer()
  const isPlaying = audioUrl !== null && playingUrl === audioUrl

  const handleClick = () => {
    if (isPlaying) {
      stop()
      return
    }
    if (audioUrl) {
      play(audioUrl)
      return
    }
    onRequestAudio(index)
  }

  const label = loading ? 'Loading…' : isPlaying ? 'Pause' : error ? 'Retry' : 'Play'

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      title={error ?? undefined}
      className="w-fit rounded border border-ink-200 px-2 py-1 text-xs font-medium text-ink-900 hover:border-ink-300 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {label}
    </button>
  )
}
