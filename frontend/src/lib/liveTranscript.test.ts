import { describe, expect, it } from 'vitest'
import { buildLiveTranscriptText, newLinesToRead } from './liveTranscript'
import type { LiveLineData } from './types'

function line(overrides: Partial<LiveLineData> = {}): LiveLineData {
  return { index: 0, original_text: 'hola', translated_text: 'hello', ...overrides }
}

describe('buildLiveTranscriptText', () => {
  it('joins translated lines with a blank line between them', () => {
    const lines = [line({ index: 0, translated_text: 'hello' }), line({ index: 1, translated_text: 'world' })]
    expect(buildLiveTranscriptText(lines)).toBe('hello\n\nworld\n')
  })

  it('skips lines with no translation yet', () => {
    const lines = [
      line({ index: 0, translated_text: 'hello' }),
      line({ index: 1, translated_text: null }),
      line({ index: 2, translated_text: 'world' }),
    ]
    expect(buildLiveTranscriptText(lines)).toBe('hello\n\nworld\n')
  })

  it('returns an empty string with no lines', () => {
    expect(buildLiveTranscriptText([])).toBe('')
  })

  it('returns an empty string when nothing is translated yet', () => {
    expect(buildLiveTranscriptText([line({ translated_text: null })])).toBe('')
  })
})

describe('newLinesToRead', () => {
  it('returns only lines after the last one already queued', () => {
    const lines = [line({ index: 0 }), line({ index: 1 }), line({ index: 2 })]
    expect(newLinesToRead(lines, 0)).toEqual({ indexes: [1, 2], lastIndex: 2 })
  })

  it('returns nothing new when every line was already seen', () => {
    const lines = [line({ index: 0 }), line({ index: 1 })]
    expect(newLinesToRead(lines, 1)).toEqual({ indexes: [], lastIndex: 1 })
  })

  it('skips a line with no translation but still marks it seen', () => {
    // Nothing to speak for it (its translation failed) - and it must not
    // be picked up again on the next render either.
    const lines = [line({ index: 0, translated_text: null }), line({ index: 1 })]
    expect(newLinesToRead(lines, -1)).toEqual({ indexes: [1], lastIndex: 1 })
  })

  it('handles an empty list', () => {
    expect(newLinesToRead([], 3)).toEqual({ indexes: [], lastIndex: 3 })
  })
})
