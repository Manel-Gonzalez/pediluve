import { useState } from 'react'
import { Button } from './Button'
import { Dialog } from './Dialog'

type ConfirmDialogProps = {
  open: boolean
  onClose: () => void
  title: string
  description: string
  confirmLabel: string
  pendingLabel?: string
  tone?: 'default' | 'danger'
  // Rejecting keeps the dialog open and shows the error inside it.
  onConfirm: () => Promise<void>
}

// "Are you sure?" in-app, instead of the browser's native confirm box
// (KAN-77). Focus starts on Cancel - the harmless choice - per the WAI-ARIA
// dialog guidance.
export function ConfirmDialog({
  open,
  onClose,
  title,
  description,
  confirmLabel,
  pendingLabel = 'Working…',
  tone = 'default',
  onConfirm,
}: ConfirmDialogProps) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleConfirm = async () => {
    setPending(true)
    setError(null)
    try {
      await onConfirm()
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setPending(false)
    }
  }

  const handleClose = () => {
    setError(null)
    onClose()
  }

  return (
    <Dialog open={open} onClose={handleClose} title={title} dismissible={!pending}>
      <p className="text-sm text-muted">{description}</p>
      {error && (
        <p role="alert" className="mt-3 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}
      <div className="mt-6 flex justify-end gap-2">
        <Button data-autofocus onClick={handleClose} disabled={pending}>
          Cancel
        </Button>
        <Button variant={tone === 'danger' ? 'danger' : 'primary'} onClick={handleConfirm} loading={pending}>
          {pending ? pendingLabel : confirmLabel}
        </Button>
      </div>
    </Dialog>
  )
}
