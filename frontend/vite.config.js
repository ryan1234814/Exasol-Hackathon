import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// One origin in production: FastAPI serves frontend/dist and owns /api/*.
// In dev, Vite runs on :5173 and proxies /api to the backend on :8000 so the
// exact same fetch paths work in both modes (no CORS anywhere, no code change).
export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // Keep the demo payload small (risk R5: modest local RAM).
    chunkSizeWarningLimit: 600,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
