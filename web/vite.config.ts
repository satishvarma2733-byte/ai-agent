import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // The LiveKit client (~520 kB) is its own chunk, loaded only when a supervisor listens to a call.
    chunkSizeWarningLimit: 600,
  },
  resolve: {
    alias: {
      // @/ maps to src/ — matches tsconfig.app.json paths
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5193,
    strictPort: true,
    proxy: {
      // Proxy /api and /health to the backend during dev
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/data/media': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 5193,
    strictPort: true,
  },
})
