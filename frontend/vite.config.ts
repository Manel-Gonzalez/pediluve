import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// uvicorn's dev address. The browser never calls it directly: everything
// goes through this dev server's proxy below (KAN-66).
const BACKEND = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    // Binds to all interfaces (not just localhost) so a phone on the same
    // Wi-Fi can load the QR/share link's live viewer page (KAN-50/KAN-53).
    host: true,
    // Vite rejects requests for hosts it doesn't know. A Cloudflare Quick
    // Tunnel gets a random *.trycloudflare.com name each time it starts.
    allowedHosts: ['.trycloudflare.com'],
    // The frontend only ever talks to its own origin (lib/api.ts), and these
    // forward the backend's paths to uvicorn - so localhost, the LAN and a
    // tunnel all work through this one port, with no CORS to configure.
    proxy: {
      '/api': BACKEND,
      '/ws': { target: BACKEND, ws: true },
    },
  },
})
