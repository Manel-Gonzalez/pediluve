import { liveViewPath } from './routes'

type OriginLike = { origin: string }

// The QR code must point at a phone-reachable origin, which is normally
// just the page's own origin (as loaded) - a scanning phone loads that
// same page before its own useLiveViewer ever talks to the backend.
//
// But getUserMedia (the owner's mic) only works in a secure context -
// exactly "localhost" or https - and a plain http://<LAN IP> doesn't
// qualify, so the owner has to keep recording on localhost. That leaves
// window.location.origin pointing at "localhost", which means nothing to
// a phone. VITE_SHARE_BASE_URL is the escape hatch: set it to your
// machine's LAN origin (e.g. http://192.168.1.42:5173) and the QR/share
// link uses that instead, while the owner's own page stays on localhost.
export function buildShareUrl(
  shareToken: string,
  location: OriginLike | undefined = typeof window !== 'undefined' ? window.location : undefined,
): string {
  const configuredBase = import.meta.env.VITE_SHARE_BASE_URL as string | undefined
  const origin = configuredBase || location?.origin || ''
  return `${origin}${liveViewPath(shareToken)}`
}
