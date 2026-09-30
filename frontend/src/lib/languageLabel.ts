// "es" -> "Spanish" for selects (KAN-76). Intl.DisplayNames ships with
// every modern browser, so no lookup table to maintain. Badges keep the
// short code: they're meant to be compact.
let displayNames: Intl.DisplayNames | null = null

export function languageName(code: string): string {
  if (!code) return code
  try {
    displayNames ??= new Intl.DisplayNames(['en'], { type: 'language', fallback: 'code' })
    const name = displayNames.of(code)
    // With fallback 'code', an unknown but well-formed tag comes back as
    // itself (sometimes re-cased) - keep the caller's original then.
    return name && name.toLowerCase() !== code.toLowerCase() ? name : code
  } catch {
    // RangeError for a malformed tag.
    return code
  }
}
