import { describe, expect, it } from 'vitest'
import { isNearBottom, jumpControl, unseenCount } from './autoScroll'

describe('isNearBottom', () => {
  const view = { clientHeight: 800, scrollHeight: 2000 }

  it('is true when scrolled all the way down', () => {
    expect(isNearBottom({ ...view, scrollTop: 1200 })).toBe(true)
  })

  it('is true within the threshold of the bottom', () => {
    expect(isNearBottom({ ...view, scrollTop: 1130 })).toBe(true)
    expect(isNearBottom({ ...view, scrollTop: 1120 })).toBe(true)
  })

  it('is false once scrolled up further than the threshold', () => {
    expect(isNearBottom({ ...view, scrollTop: 1119 })).toBe(false)
    expect(isNearBottom({ ...view, scrollTop: 0 })).toBe(false)
  })

  it('is true when everything fits on screen', () => {
    expect(isNearBottom({ scrollTop: 0, clientHeight: 800, scrollHeight: 600 })).toBe(true)
  })
})

describe('unseenCount', () => {
  it('adds the new lines while the reader is scrolled up', () => {
    expect(unseenCount(2, 5, 7, false)).toBe(4)
  })

  it('resets once they are back at the bottom', () => {
    expect(unseenCount(4, 5, 7, true)).toBe(0)
  })

  it('ignores the list shrinking (a language switch rebuilds it)', () => {
    expect(unseenCount(1, 7, 7, false)).toBe(1)
    expect(unseenCount(1, 7, 3, false)).toBe(1)
  })
})

describe('jumpControl', () => {
  it('stays hidden while following the latest line', () => {
    expect(jumpControl({ pinned: true, unseen: 0 })).toBe('hidden')
  })

  it('offers a plain arrow once the reader scrolled up, even with nothing new', () => {
    expect(jumpControl({ pinned: false, unseen: 0 })).toBe('arrow')
  })

  it('shows the count once lines arrived while scrolled up', () => {
    expect(jumpControl({ pinned: false, unseen: 3 })).toBe('count')
  })
})
