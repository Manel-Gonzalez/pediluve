import { DEFAULT_TARGET_LANGUAGE } from './languageControls'
import type { SessionSummary } from './types'

type ViewLanguageSource = Pick<SessionSummary, 'role' | 'guest_language' | 'target_language'>

// Which language SessionDetailPage opens in. A guest who picked a language
// when saving the session (guest_language) sees it in that one - on-demand
// translated if it differs from the owner's stored target_language. Anyone
// else opens in the stored language, and landing on the page never spends
// a DeepL call on its own (see SessionDetailPage).
export function initialViewLanguage(session: ViewLanguageSource): {
  language: string
  needsTranslation: boolean
} {
  if (session.role === 'guest' && session.guest_language) {
    return {
      language: session.guest_language,
      needsTranslation: session.guest_language !== session.target_language,
    }
  }
  return { language: session.target_language ?? DEFAULT_TARGET_LANGUAGE, needsTranslation: false }
}

// "Untitled - <date>" for a session with no title. Shouldn't happen once
// KAN-37's create modal requires one, but keeps the list robust against
// older or malformed rows rather than rendering a blank row.
export function formatSessionTitle(session: SessionSummary): string {
  if (session.title) return session.title
  return `Untitled - ${new Date(session.created_at).toLocaleDateString()}`
}

// The ConfirmDialog body for deleting a session (KAN-77).
export function deleteConfirmationText(session: SessionSummary): string {
  const count = session.message_count
  const messages = count > 0 ? ` and its ${count} message${count === 1 ? '' : 's'}` : ''
  return `"${formatSessionTitle(session)}"${messages} will be deleted for good. This can't be undone.`
}

// Rename-in-place (KAN-39): a successful PATCH updates just the one row's
// title, not a refetch of the whole list.
export function renameSessionInList(
  sessions: SessionSummary[],
  id: string,
  title: string,
): SessionSummary[] {
  return sessions.map((s) => (s.id === id ? { ...s, title } : s))
}

// Shared by both a successful DELETE and a 404 on either rename or delete
// (the row was removed elsewhere, e.g. another tab) - either way the row no
// longer belongs in the list, and a refetch isn't needed to know that.
export function removeSessionFromList(sessions: SessionSummary[], id: string): SessionSummary[] {
  return sessions.filter((s) => s.id !== id)
}
