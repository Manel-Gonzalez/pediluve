// "3 hours ago" for the session list (KAN-78); the full date goes in a
// tooltip. After a week a plain date reads better than "23 days ago".
const format = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

export function relativeTime(iso: string, now: Date = new Date()): string {
  const date = new Date(iso)
  const elapsed = now.getTime() - date.getTime()
  if (elapsed < MINUTE) return 'just now'
  if (elapsed < HOUR) return format.format(-Math.floor(elapsed / MINUTE), 'minute')
  if (elapsed < DAY) return format.format(-Math.floor(elapsed / HOUR), 'hour')
  if (elapsed < 7 * DAY) return format.format(-Math.floor(elapsed / DAY), 'day')
  return date.toLocaleDateString()
}
