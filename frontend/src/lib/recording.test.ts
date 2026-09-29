import { describe, expect, it } from 'vitest'
import { recordButtonLabel } from './recording'

describe('recordButtonLabel', () => {
  it('says "Start recording" before anything has ever been recorded', () => {
    expect(recordButtonLabel('idle', false)).toBe('Start recording')
  })

  it('says "Pause" while actively recording, whether or not it has recorded before', () => {
    expect(recordButtonLabel('recording', false)).toBe('Pause')
    expect(recordButtonLabel('recording', true)).toBe('Pause')
  })

  it('says "Resume recording" when idle after having recorded before', () => {
    expect(recordButtonLabel('idle', true)).toBe('Resume recording')
  })

  it('says "Resume recording" after an error, once something has already been recorded', () => {
    expect(recordButtonLabel('error', true)).toBe('Resume recording')
  })

  it('says "Start recording" after an error, if nothing has been recorded yet', () => {
    expect(recordButtonLabel('error', false)).toBe('Start recording')
  })
})
