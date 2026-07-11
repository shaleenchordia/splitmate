import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // In dev the Django API runs on :8000; in production Django serves
      // the built app itself, so /api is same-origin.
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    // Django's whitenoise serves this directory directly.
    outDir: '../backend/staticfiles',
    emptyOutDir: true,
  },
})
