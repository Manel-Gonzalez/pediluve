import { useCallback, useRef, useState } from 'react'

type RecordingStatus = 'idle' | 'recording' | 'error'

export function useMicrophone(onChunk: (chunk: Blob) => void, chunkDurationMs: number) {
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const [status, setStatus] = useState<RecordingStatus>('idle')

  const start = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) onChunk(event.data)
      }
      recorder.start(chunkDurationMs)
      recorderRef.current = recorder
      setStatus('recording')
    } catch {
      setStatus('error')
    }
  }, [onChunk, chunkDurationMs])

  const stop = useCallback(() => {
    recorderRef.current?.stop()
    streamRef.current?.getTracks().forEach((track) => track.stop())
    recorderRef.current = null
    streamRef.current = null
    setStatus('idle')
  }, [])

  return { status, start, stop }
}
