import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: 'localhost',
    port: 5173,
    // the API only lets in localhost:5173, so fail loudly instead of quietly moving port
    strictPort: true,
    proxy: {
      // the browser only ever talks to Vite, which passes /api on to clearsift serve
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
