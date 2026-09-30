// Per-line playback (KAN-33/KAN-58): first click requests the audio (a
// cache miss costs one ElevenLabs call server-side, a hit is instant), a
// later click just replays the signed URL already held.
//
// playingUrl/play/stop come from a single useAudioPlayer() instance owned
// by the page, not one per button - a page renders one PlayButton per
// line, and they must share one underlying <audio> element so starting
// line B's playback stops line A's, rather than both playing at once.
export function PlayButton({
  index,
  audioUrl,
  loading,
  error,
  onRequestAudio,
  playingUrl,
  play,
  stop,
}: {
  index: number
  audioUrl: string | null
  loading: boolean
  error: string | null
  onRequestAudio: (index: number) => void
  playingUrl: string | null
  play: (url: string) => void
  stop: () => void
}) {
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
