// Narrower than TranscriptMessage/MessageRecord (the live-view WS row and the
// REST history row respectively) - both satisfy this structurally, so these
// helpers work for either without either page needing to reshape its data.
export type TranslatedRow = {
  translated_text: string | null
  target_language: string | null
}

// target_language stays the language captured at translation time even when
// translated_text is null because DeepL failed (see backend/routers/ws.py) - so
// these two null checks are enough to tell "never asked to translate" apart from
// "asked, but it failed", without any extra frontend-side state.
export function describeTranslation(row: TranslatedRow): string {
  if (row.target_language === null) return 'Select a target language'
  if (row.translated_text === null) return 'Translation unavailable'
  return row.translated_text
}

// Single source of truth for "no real translation to show yet", so the row's
// text (describeTranslation) and its styling never disagree.
export function isTranslationPending(row: TranslatedRow): boolean {
  return row.translated_text === null
}
