import { describeTranslation, isTranslationPending, type TranslatedRow } from '../lib/transcript'

// Shared by LiveSessionPage (WS TranscriptMessage rows) and SessionDetailPage
// (REST MessageRecord rows, KAN-26) - both satisfy TranslatedRow structurally.
type TranscriptRowData = TranslatedRow & { original_text: string }

export function TranscriptRow({ row }: { row: TranscriptRowData }) {
  return (
    <div className="transcript-row">
      <p className="original">{row.original_text}</p>
      <p className={isTranslationPending(row) ? 'translated pending' : 'translated'}>
        {describeTranslation(row)}
      </p>
    </div>
  )
}
