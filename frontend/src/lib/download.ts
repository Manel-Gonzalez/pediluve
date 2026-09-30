// Shared by the anonymous viewer's client-built download and
// SessionDetailPage's authenticated one. Mirrors the backend's own
// _transcript_filename (routers/sessions.py) - the frontend names the file
// itself because Content-Disposition isn't readable cross-origin from
// fetch() without exposing it via CORS, which isn't worth it for this.
export function transcriptFilename(title: string | null, language: string | null): string {
  const name = title || 'session'
  return language ? `${name} (${language}).txt` : `${name}.txt`
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
