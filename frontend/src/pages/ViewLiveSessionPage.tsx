import { Link, useParams } from 'react-router-dom'
import { TranscriptRow } from '../components/TranscriptRow'
import { useLiveViewer } from '../hooks/useLiveViewer'
import { SUPPORTED_LANGUAGES } from '../lib/languageControls'

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
  const { joinStatus, title, sourceLanguage, state, lines, targetLanguage, setTargetLanguage } =
    useLiveViewer(shareToken)

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

      <label className="my-4 flex w-fit flex-col gap-1 text-sm text-ink-900">
        Your language
        <select
          value={targetLanguage}
          disabled={joinStatus !== 'joined'}
          onChange={(event) => setTargetLanguage(event.target.value)}
          className="rounded border border-ink-200 px-2 py-1 text-sm disabled:cursor-not-allowed disabled:opacity-50"
        >
          {SUPPORTED_LANGUAGES.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </select>
      </label>

      <div className="my-4 flex flex-col gap-3">
        {lines.map((line) => (
          <TranscriptRow
            key={line.index}
            row={{
              original_text: line.original_text,
              translated_text: line.translated_text,
              target_language: targetLanguage,
            }}
            sourceLanguage={sourceLanguage}
          />
        ))}
        {joinStatus === 'joining' && <p className="text-sm text-ink-500">Connecting…</p>}
        {joinStatus === 'joined' && lines.length === 0 && (
          <p className="text-sm text-ink-500">Nothing said yet.</p>
        )}
      </div>
    </div>
  )
}
