import { useEffect, useId, useRef, type MouseEvent, type ReactNode } from 'react'

type DialogProps = {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  // False while an action is in flight: Esc and backdrop clicks are ignored.
  dismissible?: boolean
}

// A modal on the native <dialog> element (KAN-77). showModal() gives the
// top layer, an inert page behind it and a focus trap for free; this adds
// what it doesn't: backdrop-click to close, focusing the element marked
// `data-autofocus` on open, and handing focus back to whatever opened it.
export function Dialog({ open, onClose, title, children, dismissible = true }: DialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const returnFocusRef = useRef<HTMLElement | null>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) {
      returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
      dialog.showModal()
      dialog.querySelector<HTMLElement>('[data-autofocus]')?.focus()
    } else if (!open && dialog.open) {
      dialog.close()
    }
  }, [open])

  // Fires however the dialog closed: Esc, backdrop, or `open` turning false.
  const handleClose = () => {
    returnFocusRef.current?.focus()
    returnFocusRef.current = null
    if (open) onClose()
  }

  const handleBackdropClick = (event: MouseEvent<HTMLDialogElement>) => {
    // The inner panel fills the dialog box, so a click landing on the
    // <dialog> element itself can only be on its ::backdrop.
    if (event.target === event.currentTarget && dismissible) dialogRef.current?.close()
  }

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      onClose={handleClose}
      onCancel={(event) => {
        if (!dismissible) event.preventDefault()
      }}
      onClick={handleBackdropClick}
      className="w-[calc(100%-2rem)] max-w-md rounded-2xl border border-line bg-surface p-0 text-fg shadow-xl backdrop:bg-black/40 backdrop:backdrop-blur-sm motion-safe:open:animate-caption-in"
    >
      <div className="p-6">
        <h2 id={titleId} className="mb-2 mt-0 text-lg font-semibold tracking-tight">
          {title}
        </h2>
        {children}
      </div>
    </dialog>
  )
}
