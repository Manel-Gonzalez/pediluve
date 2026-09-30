import { describe, expect, it } from 'vitest'
import { transcriptFilename } from './download'

describe('transcriptFilename', () => {
  it('combines the title and language', () => {
    expect(transcriptFilename('Standup', 'fr')).toBe('Standup (fr).txt')
  })

  it('falls back to "session" when there is no title', () => {
    expect(transcriptFilename(null, 'fr')).toBe('session (fr).txt')
  })

  it('omits the language when there is none', () => {
    expect(transcriptFilename('Standup', null)).toBe('Standup.txt')
  })
})
