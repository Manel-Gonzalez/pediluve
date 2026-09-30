import type { LiveLineData } from './types'

// Client-side download for the anonymous live viewer (KAN-50 follow-up):
// unlike SessionDetailPage (which fetches GET /api/sessions/{id}/transcript),
// this page has no Supabase session to authenticate a REST call with - but
// it already holds every line in state via useLiveViewer, so building the
// file client-side needs no backend endpoint at all. Translation-only,
// matching what the viewer page itself shows (the original text isn't
// rendered there either - see ViewLiveSessionPage.tsx).
export function buildLiveTranscriptText(lines: LiveLineData[]): string {
  const translated = lines.map((line) => line.translated_text).filter((text): text is string => !!text)
  return translated.length ? `${translated.join('\n\n')}\n` : ''
}
