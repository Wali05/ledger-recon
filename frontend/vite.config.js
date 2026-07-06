import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // In dev, proxy calls to /reconcile and /breaks to the FastAPI backend
    // so we avoid CORS issues during local (non-Docker) development
    proxy: {
      '/reconcile': 'http://localhost:8000',
      '/breaks': 'http://localhost:8000',
      '/stats': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
