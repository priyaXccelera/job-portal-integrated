/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 38687,
    strictPort: true,
    allowedHosts: ['.trycloudflare.com'],
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } }
  },
  test: {
    environment: 'jsdom',
    globals: true
  }
})
