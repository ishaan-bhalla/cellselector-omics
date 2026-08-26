import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/health':     'http://localhost:8001',
      '/genes':      'http://localhost:8001',
      '/recommend':  'http://localhost:8001',
      '/cell-lines': 'http://localhost:8001',
      '/stats':      'http://localhost:8001',
    },
  },
})
