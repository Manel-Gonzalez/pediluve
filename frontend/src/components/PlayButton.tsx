import { Loader2, Pause, RotateCcw, Volume2 } from 'lucide-react'
import { IconButton } from './IconButton'

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
  play: (url: string, onDone?: () => void) => void
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

  const label = loading ? 'Loading audio…' : isPlaying ? 'Stop' : error ? `Retry - ${error}` : 'Listen to this line'
  const Icon = loading ? Loader2 : isPlaying ? Pause : error ? RotateCcw : Volume2

  return (
    <IconButton label={label} onClick={handleClick} disabled={loading} className="-ml-2">
      <Icon className={`h-4 w-4 ${loading ? 'motion-safe:animate-spin' : ''}`} aria-hidden />
    </IconButton>
  )
}
