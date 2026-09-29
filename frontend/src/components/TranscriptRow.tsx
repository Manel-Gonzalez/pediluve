import { describeTranslation, isTranslationPending, type TranslatedRow } from '../lib/transcript'

// Shared by LiveSessionPage (WS TranscriptMessage rows) and SessionDetailPage
// (REST MessageRecord rows, KAN-26) - both satisfy TranslatedRow structurally.
type TranscriptRowData = TranslatedRow & { original_text: string }

function LanguageBadge({ children }: { children: string }) {
  return (
    <span className="inline-block rounded bg-accent-50 px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-accent-700">
      {children}
    </span>
  )
}

// sourceLanguage is session-level (there's no per-message source language in
// the data model, only session_joined/SessionSummary's source_language), so
// callers pass down whatever they know; "Original" is the fallback for
// auto-detected/unknown input language.
export function TranscriptRow({
  row,
  sourceLanguage,
}: {
  row: TranscriptRowData
  sourceLanguage?: string | null
}) {
  const pending = isTranslationPending(row)
  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="rounded-lg border border-ink-200 p-3">
        <LanguageBadge>{sourceLanguage ?? 'Original'}</LanguageBadge>
        <p className="mt-1.5 text-sm text-ink-900">{row.original_text}</p>
      </div>
      <div className="rounded-lg border border-ink-200 p-3">
        <LanguageBadge>{row.target_language ?? 'Translation'}</LanguageBadge>
        <p className={`mt-1.5 text-sm ${pending ? 'italic text-ink-500' : 'text-ink-900'}`}>
          {describeTranslation(row)}
        </p>
      </div>
    </div>
  )
}
