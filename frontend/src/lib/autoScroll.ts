// Keeps the viewer's newest line in view unless they scrolled up to reread
// (KAN-82). How close to the bottom still counts as "following along":
const NEAR_BOTTOM_PX = 80

export function isNearBottom(
  { scrollTop, clientHeight, scrollHeight }: { scrollTop: number; clientHeight: number; scrollHeight: number },
  threshold = NEAR_BOTTOM_PX,
): boolean {
  return scrollHeight - (scrollTop + clientHeight) <= threshold
}

// Lines that arrived while the reader was scrolled up - shown on the
// "N new lines" chip. Back at the bottom, there's nothing unseen.
export function unseenCount(current: number, prevLength: number, nextLength: number, pinned: boolean): number {
  if (pinned) return 0
  return current + Math.max(0, nextLength - prevLength)
}
