import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AddToMySessions } from '../components/AddToMySessions'
import { LanguageBadge } from '../components/TranscriptRow'
import { PlayButton } from '../components/PlayButton'
import { useAudioPlayer } from '../hooks/useAudioPlayer'
import { useLiveListen } from '../hooks/useLiveListen'
import { useLiveViewer } from '../hooks/useLiveViewer'
import { SUPPORTED_LANGUAGES } from '../lib/languageControls'
import { saveBlob, transcriptFilename } from '../lib/download'
import { buildLiveTranscriptText } from '../lib/liveTranscript'

// Anonymous, read-only counterpart to LiveSessionPage (KAN-50) - reached by
// a QR code/share link, no Supabase session involved at all (see App.tsx:
// this route lives outside RequireAuth).
export function ViewLiveSessionPage() {
  const { shareToken } = useParams<{ shareToken: string }>()
  if (!shareToken) return null
  return <ViewLiveSessionPageContent key={shareToken} shareToken={shareToken} />
}

function describeState(state: string | null): string {
  if (state === 'recording') return 'Recording'
  if (state === 'paused') return 'Paused'
  if (state === 'ended') return 'Session ended'
  return 'Connecting…'
}

function ViewLiveSessionPageContent({ shareToken }: { shareToken: string }) {
  const {
    joinStatus,
    title,
    state,
    lines,
    targetLanguage,
    setTargetLanguage,
    audioUrls,
    audioErrors,
    audioLoading,
    requestAudio,
  } = useLiveViewer(shareToken)
  // One shared player, not one per line (PlayButton) - starting line B's
  // playback must stop line A's, not play both at once.
  const { playingUrl, play, stop, unlock } = useAudioPlayer()
  const listen = useLiveListen({ lines, audioUrls, audioErrors, requestAudio, play, stop, unlock })
  const transcriptText = buildLiveTranscriptText(lines)
  // The line whose Play was tapped before its audio existed yet - played
  // automatically once audio_ready arrives, so that first tap isn't just
  // a silent "fetch" that needs a second tap to actually hear anything.
  const [pendingPlayIndex, setPendingPlayIndex] = useState<number | null>(null)

  useEffect(() => {
    if (pendingPlayIndex === null) return
    const url = audioUrls[pendingPlayIndex]
    if (url) {
      play(url)
      setPendingPlayIndex(null)
    } else if (audioErrors[pendingPlayIndex]) {
      setPendingPlayIndex(null)
    }
  }, [pendingPlayIndex, audioUrls, audioErrors, play])

  const handleRequestAudio = (index: number) => {
    // Inside the tap - lets the later auto-play (after audio_ready, not
    // itself a gesture) work on iOS.
    unlock()
    setPendingPlayIndex(index)
    requestAudio(index)
  }

  const handleLanguageChange = (language: string) => {
    setPendingPlayIndex(null)
    listen.resetQueue()
    setTargetLanguage(language)
  }

  const handleToggleListen = () => {
    if (listen.listening) {
      listen.stopListening()
      return
    }
    setPendingPlayIndex(null)
    listen.start()
  }

  const handleDownload = () => {
    const blob = new Blob([transcriptText], { type: 'text/plain;charset=utf-8' })
    saveBlob(blob, transcriptFilename(title, targetLanguage))
  }

  if (joinStatus === 'not_found') {
    return (
      <div className="mx-auto max-w-2xl px-4 py-8">
        <p>This live session isn't available - it may have ended, or the link may be wrong.</p>
        <Link to="/" className="text-accent-500 hover:text-accent-600">
          Go home
        </Link>
      </div>
    )
  }

  const isRecording = state === 'recording'

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="text-2xl font-semibold text-ink-900">{title ?? 'Live session'}</h1>
      <p className="mt-1 flex items-center gap-2 text-sm text-ink-500">
        {describeState(state)}
        {isRecording && (
          <span className="relative flex h-3 w-3" aria-label="Recording" role="status">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-400 opacity-75" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-accent-500" />
          </span>
        )}
      </p>

      {joinStatus === 'joined' && (
        <div className="my-4">
          <AddToMySessions shareToken={shareToken} targetLanguage={targetLanguage} />
        </div>
      )}

      <div className="my-4 flex flex-wrap items-end gap-4">
        <button
          onClick={handleToggleListen}
          disabled={joinStatus !== 'joined'}
          aria-pressed={listen.listening}
          className={`rounded px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${
            listen.listening
              ? 'bg-accent-500 text-white hover:bg-accent-600'
              : 'border border-accent-500 text-accent-600 hover:bg-accent-50'
          }`}
        >
          {listen.listening ? 'Stop listening' : 'Listen live'}
        </button>
        <label className="flex w-fit flex-col gap-1 text-sm text-ink-900">
          Your language
          <select
            value={targetLanguage}
            disabled={joinStatus !== 'joined'}
            onChange={(event) => handleLanguageChange(event.target.value)}
            className="rounded border border-ink-200 px-2 py-1 text-sm disabled:cursor-not-allowed disabled:opacity-50"
          >
            {SUPPORTED_LANGUAGES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
        <button
          onClick={handleDownload}
          disabled={!transcriptText}
          className="rounded border border-ink-200 px-3 py-1.5 text-sm font-medium text-ink-900 hover:border-ink-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Download translation
        </button>
      </div>
      {listen.listening && (
        <p className="-mt-2 mb-4 text-xs text-ink-500">
          Reading each new line aloud as it arrives.
        </p>
      )}

      <div className="my-4 flex flex-col gap-3">
        {lines.map((line) => (
          <div
            key={line.index}
            className={`flex flex-col gap-1.5 rounded-lg border p-3 ${
              listen.currentIndex === line.index ? 'border-accent-400 bg-accent-50' : 'border-ink-200'
            }`}
          >
            <LanguageBadge>{targetLanguage}</LanguageBadge>
            <p className={`text-sm ${line.translated_text ? 'text-ink-900' : 'italic text-ink-500'}`}>
              {line.translated_text ?? 'Translating…'}
            </p>
            {/* Per-line Play only while "Listen live" is off - with it on,
                lines play themselves in order, and a manual tap would
                cut into that queue. */}
            {!listen.listening && line.translated_text && (
              <PlayButton
                index={line.index}
                audioUrl={audioUrls[line.index] ?? null}
                loading={audioLoading[line.index] ?? false}
                error={audioErrors[line.index] ?? null}
                onRequestAudio={handleRequestAudio}
                playingUrl={playingUrl}
                play={play}
                stop={stop}
              />
            )}
          </div>
        ))}
        {joinStatus === 'joining' && <p className="text-sm text-ink-500">Connecting…</p>}
        {joinStatus === 'joined' && lines.length === 0 && (
          <p className="text-sm text-ink-500">Nothing said yet.</p>
        )}
      </div>
    </div>
  )
}
