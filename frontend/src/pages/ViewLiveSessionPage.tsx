import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowDown, CircleCheck, CirclePause, Download, Headphones, Hourglass, Radio, Unplug, X } from 'lucide-react'
import { AddToMySessions } from '../components/AddToMySessions'
import { Button } from '../components/Button'
import { IconButton } from '../components/IconButton'
import { LogoMark } from '../components/LogoMark'
import { PlayButton } from '../components/PlayButton'
import { ThemeToggle } from '../components/ThemeToggle'
import { useAudioPlayer } from '../hooks/useAudioPlayer'
import { useLiveListen } from '../hooks/useLiveListen'
import { useLiveViewer } from '../hooks/useLiveViewer'
import { useStickToBottom } from '../hooks/useStickToBottom'
import { saveBlob, transcriptFilename } from '../lib/download'
import { SUPPORTED_LANGUAGES } from '../lib/languageControls'
import { languageName } from '../lib/languageLabel'
import { buildLiveTranscriptText } from '../lib/liveTranscript'
import type { LiveState } from '../lib/types'
import { recordingNotice, viewerControls, type RecordingNotice } from '../lib/viewerState'

// Anonymous, read-only counterpart to LiveSessionPage (KAN-50) - reached by
// a QR code/share link, no Supabase session involved at all (see App.tsx:
// this route lives outside RequireAuth). Built for phones first (KAN-80).
export function ViewLiveSessionPage() {
  const { shareToken } = useParams<{ shareToken: string }>()
  if (!shareToken) return null
  return <ViewLiveSessionPageContent key={shareToken} shareToken={shareToken} />
}

function ViewLiveSessionPageContent({ shareToken }: { shareToken: string }) {
  const {
    joinStatus,
    title,
    state,
    speaking,
    seenRecording,
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
  // Closing the pause overlay once (KAN-84) holds for the rest of the
  // visit: later pauses show the slim bar, not the blur again.
  const [overlayDismissed, setOverlayDismissed] = useState(false)
  const controls = viewerControls({
    joinStatus,
    state,
    speaking,
    seenRecording,
    linesCount: lines.length,
    overlayDismissed,
  })
  const notice = useRecordingNotice(state, seenRecording || lines.length > 0)
  const transcriptText = buildLiveTranscriptText(lines)
  const { unseen, jumpToLatest } = useStickToBottom(lines.length, controls.showSpeaking)
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

  // The session ended: "Listen live" finishes the line it's on, then stops.
  const { listening, finishAndStop } = listen
  useEffect(() => {
    if (controls.showEndedNotice && listening) finishAndStop()
  }, [controls.showEndedNotice, listening, finishAndStop])

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
      <div className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
        <ThemeToggle className="absolute right-4 top-4" />
        <span className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-full bg-subtle text-muted">
          <Unplug className="h-6 w-6" aria-hidden />
        </span>
        <h1 className="text-xl font-semibold tracking-tight">This session isn't live</h1>
        <p className="mt-2 max-w-sm text-sm text-muted">
          It may have ended, or the link may be wrong. If you added it to your sessions, you'll find the full
          transcript there.
        </p>
        <Link to="/" className="mt-6 text-sm font-medium text-primary hover:text-primary-hover">
          Go to my sessions
        </Link>
      </div>
    )
  }

  const downloadButton = (
    <IconButton label="Download translation" onClick={handleDownload} disabled={!transcriptText}>
      <Download className="h-5 w-5" aria-hidden />
    </IconButton>
  )

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-line bg-canvas/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-2xl items-center gap-3 px-4">
          <LogoMark className="h-7 w-7 shrink-0" />
          <h1 className="min-w-0 flex-1 truncate text-base font-semibold tracking-tight">
            {title ?? 'Live session'}
          </h1>
          <LivePill
            state={joinStatus === 'joined' ? state : null}
            notStarted={controls.overlay === 'not_started' || controls.statusBar === 'not_started'}
          />
          <ThemeToggle />
        </div>
        {controls.statusBar !== 'none' && <WaitingBar kind={controls.statusBar} />}
      </header>

      {notice && state === 'recording' && <RecordingToast key={notice.id} kind={notice.kind} />}

      <main className="mx-auto max-w-2xl px-4 pb-16 pt-4">
        {controls.showEndedNotice ? (
          <section className="mb-6 rounded-xl border border-line bg-surface p-5">
            <div className="flex items-start gap-3">
              <CircleCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
              <div className="flex-1">
                <h2 className="font-semibold tracking-tight">This session has ended</h2>
                <p className="mt-1 text-sm text-muted">Thanks for following along. Keep a copy before you go:</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={handleDownload}
                    disabled={!transcriptText}
                    icon={<Download className="h-4 w-4" aria-hidden />}
                  >
                    Download translation
                  </Button>
                  <AddToMySessions shareToken={shareToken} targetLanguage={targetLanguage} />
                </div>
              </div>
            </div>
          </section>
        ) : (
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant={listen.listening ? 'primary' : 'secondary'}
              onClick={handleToggleListen}
              disabled={!controls.listenAvailable}
              aria-pressed={listen.listening}
              icon={<Headphones className="h-4 w-4" aria-hidden />}
            >
              {listen.listening ? 'Stop listening' : 'Listen live'}
            </Button>
            <label className="sr-only" htmlFor="viewer-language">
              Your language
            </label>
            <select
              id="viewer-language"
              value={targetLanguage}
              disabled={controls.languageLocked}
              onChange={(event) => handleLanguageChange(event.target.value)}
              className="h-8 rounded-lg border border-line px-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
            >
              {SUPPORTED_LANGUAGES.map((code) => (
                <option key={code} value={code}>
                  {languageName(code)}
                </option>
              ))}
            </select>
            <div className="ml-auto flex items-center gap-1">
              {joinStatus === 'joined' && (
                <AddToMySessions shareToken={shareToken} targetLanguage={targetLanguage} compact />
              )}
              {downloadButton}
            </div>
          </div>
        )}
        {listen.listening && (
          <p className="-mt-2 mb-4 text-xs text-muted">Reading each new line aloud as it arrives.</p>
        )}

        <section aria-label="Live translation" className="relative min-h-[50vh]">
          <div className="flex flex-col gap-3">
            {lines.map((line) => {
              const cached = audioUrls[line.index] !== undefined
              const showPlay =
                !listen.listening && !!line.translated_text && (controls.perLinePlay === 'all' || cached)
              return (
                <article
                  key={line.index}
                  className={`flex items-start gap-2 rounded-xl border px-4 py-3 transition-colors ${
                    listen.currentIndex === line.index ? 'border-primary bg-highlight' : 'border-line bg-surface'
                  }`}
                >
                  <p
                    className={`flex-1 text-lg leading-relaxed ${line.translated_text ? 'text-fg' : 'italic text-muted'}`}
                  >
                    {line.translated_text ?? 'Translating…'}
                  </p>
                  {/* Per-line Play only while "Listen live" is off - with it
                      on, lines play themselves in order, and a manual tap
                      would cut into that queue. */}
                  {showPlay && (
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
                </article>
              )
            })}
            {controls.showSpeaking && <SpeakingBubble />}
            {joinStatus === 'joining' && <p className="text-sm text-muted">Connecting…</p>}
            {joinStatus === 'joined' && state === 'recording' && lines.length === 0 && !speaking && (
              <p className="text-sm text-muted">Nothing said yet.</p>
            )}
          </div>

          {controls.overlay !== 'none' && (
            <WaitingOverlay kind={controls.overlay} onDismiss={() => setOverlayDismissed(true)} />
          )}
        </section>

        {unseen > 0 && (
          <div className="pointer-events-none fixed inset-x-0 bottom-6 z-20 flex justify-center">
            <Button
              variant="primary"
              size="sm"
              onClick={jumpToLatest}
              icon={<ArrowDown className="h-4 w-4" aria-hidden />}
              className="pointer-events-auto rounded-full shadow-lg"
            >
              {unseen} new line{unseen === 1 ? '' : 's'}
            </Button>
          </div>
        )}
      </main>
    </div>
  )
}

function LivePill({ state, notStarted }: { state: LiveState | null; notStarted: boolean }) {
  if (state === 'recording') {
    return (
      <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-highlight px-2.5 py-1 text-xs font-medium text-highlight-fg">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full rounded-full bg-accent-400 opacity-75 motion-safe:animate-ping" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
        </span>
        Live
      </span>
    )
  }
  const label = notStarted ? 'Waiting' : state === 'paused' ? 'Paused' : state === 'ended' ? 'Ended' : 'Connecting'
  return (
    <span className="inline-flex shrink-0 items-center rounded-full bg-subtle px-2.5 py-1 text-xs font-medium text-muted">
      {label}
    </span>
  )
}

const WAITING = {
  paused: { Icon: CirclePause, title: 'Paused', detail: 'Waiting for the recording to resume…' },
  not_started: { Icon: Hourglass, title: 'Not started yet', detail: 'Waiting for the recording to start…' },
}

// Blurs the transcript while the owner is paused, or hasn't started yet
// (KAN-80) - so a still screen reads as "on purpose", not as broken. Only
// the transcript: the language, Listen live and download stay usable. It
// can be closed (KAN-84) to read or play earlier lines during the pause.
function WaitingOverlay({ kind, onDismiss }: { kind: 'not_started' | 'paused'; onDismiss: () => void }) {
  const { Icon, title, detail } = WAITING[kind]
  return (
    <div className="absolute inset-0 z-10 flex items-start justify-center rounded-xl bg-canvas/60 pt-16 backdrop-blur-sm">
      <div className="relative mx-4 flex max-w-xs flex-col items-center rounded-2xl border border-line bg-surface px-8 py-5 text-center shadow-xl">
        <IconButton label="Hide this notice" onClick={onDismiss} className="absolute right-1 top-1">
          <X className="h-4 w-4" aria-hidden />
        </IconButton>
        <Icon className="mb-2 h-6 w-6 text-primary" aria-hidden />
        <div role="status" aria-live="polite">
          <p className="font-medium">{title}</p>
          <p className="mt-1 text-sm text-muted">{detail}</p>
        </div>
      </div>
    </div>
  )
}

// What the overlay becomes once closed: one line under the header, sticky
// with it, so the wait stays visible without covering anything.
function WaitingBar({ kind }: { kind: 'not_started' | 'paused' }) {
  const { Icon, title, detail } = WAITING[kind]
  return (
    <div role="status" aria-live="polite" className="border-t border-line bg-subtle">
      <p className="mx-auto flex max-w-2xl items-center gap-2 px-4 py-1.5 text-xs text-muted">
        <Icon className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
        <span className="font-medium text-fg">{title}</span>
        <span className="truncate">- {detail}</span>
      </p>
    </div>
  )
}

const TOAST_MS = 4000

// Watches for the owner pressing record again (KAN-84). Each notice gets
// its own id, so a quick pause/resume restarts the toast instead of being
// swallowed by the one still on screen.
function useRecordingNotice(state: LiveState | null, recordedBefore: boolean) {
  const [notice, setNotice] = useState<{ kind: RecordingNotice; id: number } | null>(null)
  const previous = useRef({ state, recordedBefore })

  useEffect(() => {
    const kind = recordingNotice({
      previous: previous.current.state,
      next: state,
      recordedBefore: previous.current.recordedBefore,
    })
    previous.current = { state, recordedBefore }
    if (kind) setNotice({ kind, id: Date.now() })
  }, [state, recordedBefore])

  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => setNotice(null), TOAST_MS)
    return () => clearTimeout(timer)
  }, [notice])

  return notice
}

function RecordingToast({ kind }: { kind: RecordingNotice }) {
  return (
    <div className="pointer-events-none fixed inset-x-0 top-20 z-30 flex justify-center px-4">
      <p
        role="status"
        className="flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary shadow-lg motion-safe:animate-caption-in"
      >
        <Radio className="h-4 w-4" aria-hidden />
        {kind === 'resumed' ? 'Recording resumed' : 'Recording started'}
      </p>
    </div>
  )
}

// KAN-65: shown while the owner is mid-sentence - viewers only ever get
// committed, translated lines, so without it the screen just sits still
// until the whole sentence lands.
function SpeakingBubble() {
  return (
    <div
      role="status"
      aria-label="The speaker is talking"
      className="flex w-fit items-center gap-1 rounded-xl border border-line bg-surface px-4 py-3"
    >
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="h-2 w-2 rounded-full bg-accent-400 motion-safe:animate-bounce"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  )
}
