import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite will output to ../frontend/build for Flask to serve
export default defineConfig({
  plugins: [react()],
  root: './',
  build: {
    outDir: '../frontend/build',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // Proxy API calls to Flask backend
      '/sessions': { target: 'http://127.0.0.1:5000', changeOrigin: true },
      '/chat': { target: 'http://127.0.0.1:5000', changeOrigin: true },
    },
  },
})
