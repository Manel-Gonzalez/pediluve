import { AudioLines } from 'lucide-react'

// The app's mark: a waveform on the primary color - same shape as the
// favicon (public/favicon.svg).
export function LogoMark({ className = 'h-7 w-7' }: { className?: string }) {
  return (
    <span className={`inline-flex items-center justify-center rounded-lg bg-primary text-on-primary ${className}`}>
      <AudioLines className="h-4 w-4" aria-hidden />
    </span>
  )
}
