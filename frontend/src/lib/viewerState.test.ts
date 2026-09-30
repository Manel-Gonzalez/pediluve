import { describe, expect, it } from 'vitest'
import { viewerControls } from './viewerState'

const joined = { joinStatus: 'joined' as const, speaking: false, seenRecording: false, linesCount: 0 }

describe('viewerControls', () => {
  it('shows nothing extra while still joining', () => {
    const controls = viewerControls({ ...joined, joinStatus: 'joining', state: null })
    expect(controls.overlay).toBe('none')
    expect(controls.showEndedNotice).toBe(false)
    expect(controls.languageLocked).toBe(true)
    expect(controls.listenAvailable).toBe(false)
  })

  it('says "not started" when paused before anything was ever recorded', () => {
    // A room starts out "paused" until the owner first presses record.
    expect(viewerControls({ ...joined, state: 'paused' }).overlay).toBe('not_started')
  })

  it('says "paused" once recording has happened', () => {
    expect(viewerControls({ ...joined, state: 'paused', seenRecording: true }).overlay).toBe('paused')
  })

  it('treats earlier lines (a resumed session) as having recorded before', () => {
    expect(viewerControls({ ...joined, state: 'paused', linesCount: 3 }).overlay).toBe('paused')
  })

  it('clears the overlay and shows the speaking bubble while recording', () => {
    const controls = viewerControls({ ...joined, state: 'recording', speaking: true, seenRecording: true })
    expect(controls.overlay).toBe('none')
    expect(controls.showSpeaking).toBe(true)
    expect(controls.languageLocked).toBe(false)
    expect(controls.listenAvailable).toBe(true)
    expect(controls.perLinePlay).toBe('all')
  })

  it('never shows the speaking bubble unless recording', () => {
    expect(viewerControls({ ...joined, state: 'paused', speaking: true }).showSpeaking).toBe(false)
  })

  it('settles into a final state once the session ends', () => {
    const controls = viewerControls({ ...joined, state: 'ended', speaking: true, seenRecording: true, linesCount: 5 })
    expect(controls).toEqual({
      overlay: 'none',
      showEndedNotice: true,
      showSpeaking: false,
      languageLocked: true,
      listenAvailable: false,
      perLinePlay: 'cached_only',
    })
  })
})
