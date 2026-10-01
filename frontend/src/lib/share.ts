import { liveViewPath } from './routes'

type OriginLike = { origin: string }

const LOCALHOST_NAMES = new Set(['localhost', '127.0.0.1', '[::1]'])

// The QR code must point at a phone-reachable origin, which is normally
// just the page's own origin (as loaded) - a scanning phone loads that
// same page before its own useLiveViewer ever talks to the backend.
//
// The exception is localhost. getUserMedia (the owner's mic) only works in
// a secure context - "localhost" or https - so on the LAN the owner records
// on http://localhost:5173, and a QR saying "localhost" would send the
// phone to itself. VITE_SHARE_BASE_URL fills that gap: set it to your
// machine's LAN origin (e.g. http://192.168.1.42:5173). It only applies
// while the page itself is on localhost: an owner recording through an
// https tunnel (KAN-66) already has a reachable origin, and the QR should
// carry that one.
export function buildShareUrl(
  shareToken: string,
  location: OriginLike | undefined = typeof window !== 'undefined' ? window.location : undefined,
): string {
  const configuredBase = import.meta.env.VITE_SHARE_BASE_URL as string | undefined
  const origin = location?.origin || ''
  const onLocalhost = !origin || LOCALHOST_NAMES.has(new URL(origin).hostname)
  const base = onLocalhost && configuredBase ? configuredBase : origin
  return `${base}${liveViewPath(shareToken)}`
}
