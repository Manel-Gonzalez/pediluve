import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import { buildShareUrl } from '../lib/share'

// Lets anyone on the same network scan into a read-only live view of this
// session (KAN-50) - the share_token is a bearer capability link, so this
// is the only UI that ever exposes it.
export function SharePanel({ shareToken }: { shareToken: string }) {
  const shareUrl = buildShareUrl(shareToken)
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let cancelled = false
    QRCode.toDataURL(shareUrl, { margin: 1, width: 160 })
      .then((dataUrl) => {
        if (!cancelled) setQrDataUrl(dataUrl)
      })
      .catch(() => {
        if (!cancelled) setQrDataUrl(null)
      })
    return () => {
      cancelled = true
    }
  }, [shareUrl])

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard access can be denied (permissions, non-secure context) -
      // the link is still selectable/copyable by hand right below the button.
    }
  }

  return (
    <div className="my-4 flex flex-wrap items-center gap-4 rounded-lg border border-ink-200 p-3">
      {qrDataUrl && (
        <img src={qrDataUrl} alt="QR code to the live view of this session" width={112} height={112} />
      )}
      <div className="flex min-w-0 flex-col gap-1.5">
        <p className="text-sm font-medium text-ink-900">Share this session</p>
        <p className="max-w-xs truncate text-xs text-ink-500">{shareUrl}</p>
        <button
          onClick={handleCopy}
          className="w-fit rounded border border-ink-200 px-2 py-1 text-xs font-medium text-ink-900 hover:border-ink-300"
        >
          {copied ? 'Copied!' : 'Copy link'}
        </button>
      </div>
    </div>
  )
}
