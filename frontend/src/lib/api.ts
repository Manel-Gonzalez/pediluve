export function getWebSocketUrl(): string {
  return import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws'
}

export function getChunkDurationMs(): number {
  return Number(import.meta.env.VITE_CHUNK_DURATION_MS) || 250
}
