import type { OwnerStatus } from '../lib/liveStatus'

const LABELS: Record<OwnerStatus, string> = {
  connecting: 'Connecting…',
  ready: 'Ready',
  recording: 'Recording',
  paused: 'Paused',
  disconnected: 'Disconnected',
  mic_error: 'Microphone unavailable',
}

// The owner's live status in one pill (KAN-81), from lib/liveStatus.ts.
export function StatusPill({ status }: { status: OwnerStatus }) {
  const tone =
    status === 'recording'
      ? 'bg-highlight text-highlight-fg'
      : status === 'disconnected' || status === 'mic_error'
        ? 'bg-danger-soft text-danger'
        : 'bg-subtle text-muted'
  return (
    <span
      role="status"
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${tone}`}
    >
      {status === 'recording' && (
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full rounded-full bg-accent-400 opacity-75 motion-safe:animate-ping" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
        </span>
      )}
      {LABELS[status]}
    </span>
  )
}
