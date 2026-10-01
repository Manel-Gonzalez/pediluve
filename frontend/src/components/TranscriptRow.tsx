import { describeTranslation, isTranslationPending, type TranslatedRow } from '../lib/transcript'

// Shared by LiveSessionPage (WS TranscriptMessage rows) and SessionDetailPage
// (REST MessageRecord rows, KAN-26) - both satisfy TranslatedRow structurally.
type TranscriptRowData = TranslatedRow & { original_text: string }

export function LanguageBadge({ children }: { children: string }) {
  return (
    <span className="inline-block rounded-full bg-highlight px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-highlight-fg">
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
    <div className="grid overflow-hidden rounded-xl border border-line bg-surface sm:grid-cols-2">
      <div className="border-b border-line p-4 sm:border-b-0 sm:border-r">
        <LanguageBadge>{sourceLanguage ?? 'Original'}</LanguageBadge>
        <p className="mt-2 text-muted">{row.original_text}</p>
      </div>
      <div className="p-4">
        <LanguageBadge>{row.target_language ?? 'Translation'}</LanguageBadge>
        <p className={`mt-2 ${pending ? 'italic text-muted' : 'text-fg'}`}>{describeTranslation(row)}</p>
      </div>
    </div>
  )
}
