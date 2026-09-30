import { Loader2 } from 'lucide-react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

export const FOCUS_RING =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-primary text-on-primary hover:bg-primary-hover',
  secondary: 'border border-line bg-surface text-fg hover:border-line-strong hover:bg-subtle',
  ghost: 'text-muted hover:bg-subtle hover:text-fg',
  danger: 'bg-danger text-on-primary hover:bg-danger/90',
}

const SIZES: Record<Size, string> = {
  sm: 'h-8 gap-1.5 px-3 text-sm',
  md: 'h-10 gap-2 px-4 text-sm',
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  size?: Size
  loading?: boolean
  icon?: ReactNode
}

// The app's one button style (KAN-76). `icon` sits before the label; while
// `loading`, a spinner replaces it and the button is disabled.
export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  icon,
  disabled,
  className = '',
  children,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING} ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  )
}
