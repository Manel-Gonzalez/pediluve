// HomePage's session list, 10 per page with the page in the URL (?page=N)
// so a reload or the Back button keeps it (KAN-78). Pages are 1-based.
export const PAGE_SIZE = 10

export function parsePageParam(raw: string | null): number {
  const page = Number(raw)
  return Number.isInteger(page) && page >= 1 ? page : 1
}

export function pageCount(total: number, size: number): number {
  return Math.max(1, Math.ceil(total / size))
}

export function clampPage(page: number, count: number): number {
  return Math.min(Math.max(page, 1), count)
}

export function offsetForPage(page: number, size: number): number {
  return (page - 1) * size
}

// The page to show after a row was removed, given the new total: the same
// one unless it just became empty (the last row of the last page).
export function pageAfterRemoval(page: number, totalAfter: number, size: number): number {
  return clampPage(page, pageCount(totalAfter, size))
}

export function rangeLabel(page: number, size: number, total: number): string {
  if (total === 0) return ''
  const first = offsetForPage(page, size) + 1
  const last = Math.min(first + size - 1, total)
  return `${first}–${last} of ${total}`
}
