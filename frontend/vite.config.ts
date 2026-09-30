import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Binds to all interfaces (not just localhost) so a phone on the same
    // Wi-Fi can load the QR/share link's live viewer page (KAN-50/KAN-53).
    // The mic-capturing owner view still needs a secure context, so keep
    // recording on http://localhost:5173 - only the viewer needs the LAN IP.
    host: true,
  },
})
