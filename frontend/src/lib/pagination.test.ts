import { describe, expect, it } from 'vitest'
import {
  PAGE_SIZE,
  clampPage,
  offsetForPage,
  pageAfterRemoval,
  pageCount,
  parsePageParam,
  rangeLabel,
} from './pagination'

describe('PAGE_SIZE', () => {
  it('shows ten sessions per page', () => {
    expect(PAGE_SIZE).toBe(10)
  })
})

describe('parsePageParam', () => {
  it('reads a positive page number from ?page=', () => {
    expect(parsePageParam('3')).toBe(3)
  })

  it('treats a missing, non-numeric, fractional or < 1 value as page 1', () => {
    expect(parsePageParam(null)).toBe(1)
    expect(parsePageParam('abc')).toBe(1)
    expect(parsePageParam('2.5')).toBe(1)
    expect(parsePageParam('0')).toBe(1)
    expect(parsePageParam('-4')).toBe(1)
  })
})

describe('pageCount', () => {
  it('always has at least one page, even with nothing in it', () => {
    expect(pageCount(0, 10)).toBe(1)
  })

  it('rounds up a partial last page', () => {
    expect(pageCount(10, 10)).toBe(1)
    expect(pageCount(11, 10)).toBe(2)
    expect(pageCount(67, 10)).toBe(7)
  })
})

describe('clampPage', () => {
  it('keeps a page within 1..count', () => {
    expect(clampPage(3, 7)).toBe(3)
    expect(clampPage(999, 7)).toBe(7)
    expect(clampPage(0, 7)).toBe(1)
  })
})

describe('offsetForPage', () => {
  it('turns a 1-based page into an API offset', () => {
    expect(offsetForPage(1, 10)).toBe(0)
    expect(offsetForPage(3, 10)).toBe(20)
  })
})

describe('pageAfterRemoval', () => {
  it('stays on the page while it still has rows', () => {
    expect(pageAfterRemoval(2, 15, 10)).toBe(2)
  })

  it('steps back when the last row of the last page goes', () => {
    // 11 sessions -> page 2 held one; after deleting it, 10 remain.
    expect(pageAfterRemoval(2, 10, 10)).toBe(1)
  })

  it('never goes below page 1', () => {
    expect(pageAfterRemoval(1, 0, 10)).toBe(1)
  })
})

describe('rangeLabel', () => {
  it('describes which rows are on screen', () => {
    expect(rangeLabel(2, 10, 67)).toBe('11–20 of 67')
    expect(rangeLabel(7, 10, 67)).toBe('61–67 of 67')
    expect(rangeLabel(1, 10, 3)).toBe('1–3 of 3')
  })

  it('is empty when there is nothing to show', () => {
    expect(rangeLabel(1, 10, 0)).toBe('')
  })
})
