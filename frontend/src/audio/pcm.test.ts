import { describe, expect, it } from 'vitest'
import { floatTo16BitPCM } from './pcm'

describe('floatTo16BitPCM', () => {
  it('converts silence to zeroed samples', () => {
    const result = new Int16Array(floatTo16BitPCM(new Float32Array([0, 0, 0])))
    expect(Array.from(result)).toEqual([0, 0, 0])
  })

  it('maps full-scale positive and negative samples to Int16 bounds', () => {
    const result = new Int16Array(floatTo16BitPCM(new Float32Array([1, -1])))
    expect(result[0]).toBe(0x7fff)
    expect(result[1]).toBe(-0x8000)
  })

  it('clips out-of-range input instead of overflowing', () => {
    const result = new Int16Array(floatTo16BitPCM(new Float32Array([2.5, -3])))
    expect(result[0]).toBe(0x7fff)
    expect(result[1]).toBe(-0x8000)
  })

  it('preserves sample count and produces a buffer of the right byte length', () => {
    const input = new Float32Array(100).fill(0.5)
    const buffer = floatTo16BitPCM(input)
    expect(buffer.byteLength).toBe(100 * 2)
  })
})
