import { describe, expect, it } from 'vitest'
import { buildLiveTranscriptText } from './liveTranscript'
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
