import { useCallback, useEffect, useRef, useState } from 'react'
import { isNearBottom, unseenCount } from '../lib/autoScroll'

function scrollToBottom() {
  const smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches
  window.scrollTo({ top: document.documentElement.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
}

// The viewer page follows new lines as they arrive (KAN-82) - unless the
// reader scrolled up to reread, in which case it stays put and counts what
// they're missing. `count` is the number of lines; `extra` is anything else
// that grows the page (the speaking bubble) and should be followed too.
export function useStickToBottom(count: number, extra: unknown) {
  // Only scrolling *up* away from the bottom unpins: our own smooth scroll
  // down passes through "not at the bottom yet" positions too.
  const pinnedRef = useRef(true)
  // The same flag as state, for rendering the jump button (KAN-86) - the
  // ref is what the effects read without re-subscribing.
  const [pinned, setPinnedState] = useState(true)
  const setPinned = useCallback((value: boolean) => {
    pinnedRef.current = value
    setPinnedState(value)
  }, [])
  const lastScrollYRef = useRef(0)
  const prevCountRef = useRef(count)
  const [unseen, setUnseen] = useState(0)

  useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY
      const atBottom = isNearBottom({
        scrollTop: y,
        clientHeight: window.innerHeight,
        scrollHeight: document.documentElement.scrollHeight,
      })
      if (atBottom) {
        setPinned(true)
        setUnseen(0)
      } else if (y < lastScrollYRef.current) {
        setPinned(false)
      }
      lastScrollYRef.current = y
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [setPinned])

  useEffect(() => {
    const prev = prevCountRef.current
    prevCountRef.current = count
    if (pinnedRef.current) scrollToBottom()
    setUnseen((current) => unseenCount(current, prev, count, pinnedRef.current))
  }, [count, extra])

  const jumpToLatest = useCallback(() => {
    setPinned(true)
    setUnseen(0)
    scrollToBottom()
  }, [setPinned])

  return { unseen, pinned, jumpToLatest }
}
