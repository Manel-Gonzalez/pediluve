import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { FOCUS_RING } from './Button'

type IconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label'> & {
  // Required: an icon alone has no accessible name. Also the hover tooltip.
  label: string
  tone?: 'default' | 'danger'
  children: ReactNode
}

// A round, icon-only button (KAN-76) - 36px, 40px on touch screens.
export function IconButton({ label, tone = 'default', className = '', children, type = 'button', ...rest }: IconButtonProps) {
  const toneClass =
    tone === 'danger' ? 'text-muted hover:bg-danger-soft hover:text-danger' : 'text-muted hover:bg-subtle hover:text-fg'
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-40 [@media(pointer:coarse)]:h-10 [@media(pointer:coarse)]:w-10 ${FOCUS_RING} ${toneClass} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
