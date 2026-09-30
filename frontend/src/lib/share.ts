import { liveViewPath } from './routes'

type OriginLike = { origin: string }

// Deliberately uses the page's own origin (as loaded), not getApiUrl/
// getWebSocketUrl's backend host - the QR code must point at *this*
// frontend page (LAN IP and all, see KAN-53), which a scanning phone then
// loads before that page's own useLiveViewer talks to the backend.
export function buildShareUrl(
  shareToken: string,
  location: OriginLike | undefined = typeof window !== 'undefined' ? window.location : undefined,
): string {
  const origin = location?.origin ?? ''
  return `${origin}${liveViewPath(shareToken)}`
}
