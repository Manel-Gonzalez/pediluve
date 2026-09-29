import type { RecordingStatus } from '../hooks/useMicrophone'

// useMicrophone's RecordingStatus has no distinct "paused" state (stop()
// resets it to 'idle', the same as before ever recording) - hasRecorded is
// the page's own memory of "has this session captured audio before", so the
// button can say "Resume recording" instead of misleadingly "Start
// recording" again after a pause.
export function recordButtonLabel(micStatus: RecordingStatus, hasRecorded: boolean): string {
  if (micStatus === 'recording') return 'Pause'
  return hasRecorded ? 'Resume recording' : 'Start recording'
}
