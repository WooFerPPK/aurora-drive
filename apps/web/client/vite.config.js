import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Backend defaults to 127.0.0.1:8000 (see fh6-racer-backend/.env).
// Dev server proxies /api and /ws straight to it so the same fetch/WS
// paths the deployed (nginx-proxied) build uses also work locally.
const BACKEND = process.env.FH6_BACKEND || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/ws':  { target: BACKEND, changeOrigin: true, ws: true },
      '/healthz': { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    emptyOutDir: true,
  },
})
