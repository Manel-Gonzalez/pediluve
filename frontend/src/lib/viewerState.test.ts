import { describe, expect, it } from 'vitest'
import { recordingNotice, viewerControls } from './viewerState'

const joined = {
  joinStatus: 'joined' as const,
  speaking: false,
  seenRecording: false,
  linesCount: 0,
  overlayDismissed: false,
}

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
      statusBar: 'none',
      showEndedNotice: true,
      showSpeaking: false,
      languageLocked: true,
      listenAvailable: false,
      perLinePlay: 'cached_only',
    })
  })

  it('shows the wait as a slim bar instead, once the viewer dismissed the overlay', () => {
    const paused = viewerControls({ ...joined, state: 'paused', seenRecording: true, overlayDismissed: true })
    expect(paused.overlay).toBe('none')
    expect(paused.statusBar).toBe('paused')
    const notStarted = viewerControls({ ...joined, state: 'paused', overlayDismissed: true })
    expect(notStarted.overlay).toBe('none')
    expect(notStarted.statusBar).toBe('not_started')
  })

  it('shows no bar while the overlay is still up', () => {
    expect(viewerControls({ ...joined, state: 'paused' }).statusBar).toBe('none')
  })

  it('drops the bar while recording or once ended, even if dismissed', () => {
    expect(viewerControls({ ...joined, state: 'recording', overlayDismissed: true }).statusBar).toBe('none')
    expect(viewerControls({ ...joined, state: 'ended', overlayDismissed: true }).statusBar).toBe('none')
  })
})

describe('recordingNotice', () => {
  it('announces a resume when recording comes back after a pause', () => {
    expect(recordingNotice({ previous: 'paused', next: 'recording', recordedBefore: true })).toBe('resumed')
  })

  it('announces a start when the first recording begins', () => {
    expect(recordingNotice({ previous: 'paused', next: 'recording', recordedBefore: false })).toBe('started')
  })

  it('stays quiet when joining a session that is already recording', () => {
    // Nothing changed for the viewer - they just arrived mid-recording.
    expect(recordingNotice({ previous: null, next: 'recording', recordedBefore: false })).toBeNull()
  })

  it('stays quiet on any other change', () => {
    expect(recordingNotice({ previous: 'recording', next: 'paused', recordedBefore: true })).toBeNull()
    expect(recordingNotice({ previous: 'recording', next: 'ended', recordedBefore: true })).toBeNull()
    expect(recordingNotice({ previous: 'recording', next: 'recording', recordedBefore: true })).toBeNull()
  })
})
