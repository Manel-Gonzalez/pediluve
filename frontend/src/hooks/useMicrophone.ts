import { useCallback, useRef, useState } from 'react'
import pcmWorkletUrl from '../audio/pcm-worklet.js?url'

type RecordingStatus = 'idle' | 'recording' | 'error'

const SAMPLE_RATE = 16000

function floatTo16BitPCM(input: Float32Array): ArrayBuffer {
  const output = new Int16Array(input.length)
  for (let i = 0; i < input.length; i++) {
    const sample = Math.max(-1, Math.min(1, input[i]))
    output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
  }
  return output.buffer
}

export function useMicrophone(onChunk: (chunk: ArrayBuffer) => void, chunkDurationMs: number) {
  const audioContextRef = useRef<AudioContext | null>(null)
  const workletNodeRef = useRef<AudioWorkletNode | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const bufferRef = useRef<Float32Array[]>([])
  const bufferedSamplesRef = useRef(0)
  const [status, setStatus] = useState<RecordingStatus>('idle')

  const start = useCallback(async (): Promise<number | null> => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      const audioContext = new AudioContext({ sampleRate: SAMPLE_RATE })
      audioContextRef.current = audioContext
      const sampleRate = audioContext.sampleRate

      await audioContext.audioWorklet.addModule(pcmWorkletUrl)

      const source = audioContext.createMediaStreamSource(stream)
      const workletNode = new AudioWorkletNode(audioContext, 'pcm-worklet-processor')
      workletNodeRef.current = workletNode

      const targetSamples = (sampleRate * chunkDurationMs) / 1000

      const flush = () => {
        if (bufferedSamplesRef.current === 0) return
        const merged = new Float32Array(bufferedSamplesRef.current)
        let offset = 0
        for (const part of bufferRef.current) {
          merged.set(part, offset)
          offset += part.length
        }
        bufferRef.current = []
        bufferedSamplesRef.current = 0
        onChunk(floatTo16BitPCM(merged))
      }

      workletNode.port.onmessage = (event: MessageEvent<Float32Array>) => {
        bufferRef.current.push(event.data)
        bufferedSamplesRef.current += event.data.length
        if (bufferedSamplesRef.current >= targetSamples) flush()
      }

      source.connect(workletNode)
      setStatus('recording')
      return sampleRate
    } catch {
      setStatus('error')
      return null
    }
  }, [onChunk, chunkDurationMs])

  const stop = useCallback(() => {
    workletNodeRef.current?.disconnect()
    workletNodeRef.current = null
    audioContextRef.current?.close()
    audioContextRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    bufferRef.current = []
    bufferedSamplesRef.current = 0
    setStatus('idle')
  }, [])

  return { status, start, stop }
}
