import { useEffect, useState } from 'react'
import { Check, Copy } from 'lucide-react'
import QRCode from 'qrcode'
import { buildShareUrl } from '../lib/share'
import { Button } from './Button'

// Lets anyone on the same network scan into a read-only live view of this
// session (KAN-50) - the share_token is a bearer capability link, so this
// is the only UI that ever exposes it.
export function SharePanel({ shareToken }: { shareToken: string }) {
  const shareUrl = buildShareUrl(shareToken)
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let cancelled = false
    QRCode.toDataURL(shareUrl, { margin: 1, width: 320 })
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
    <div className="flex flex-col items-center gap-3 text-center">
      {qrDataUrl && (
        // Always dark-on-white, even in dark mode: phone cameras read that best.
        <img
          src={qrDataUrl}
          alt="QR code to the live view of this session"
          width={160}
          height={160}
          className="rounded-lg bg-white p-2 ring-1 ring-line"
        />
      )}
      <p className="text-sm text-muted">Scan to follow live, translated into your own language.</p>
      <p className="w-full select-all truncate rounded-md bg-subtle px-2 py-1 font-mono text-xs text-muted">
        {shareUrl}
      </p>
      <Button
        size="sm"
        onClick={handleCopy}
        className="w-full"
        icon={copied ? <Check className="h-4 w-4 text-primary" aria-hidden /> : <Copy className="h-4 w-4" aria-hidden />}
      >
        {copied ? 'Copied' : 'Copy link'}
      </Button>
    </div>
  )
}
