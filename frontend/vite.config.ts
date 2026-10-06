import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the dashboard runs on Vite (5173) and talks to the gateway on 8000.
// In production FastAPI serves the built files, so no proxy is involved.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
