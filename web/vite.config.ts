import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    // MapLibre GL is a single ~1 MB library; keep it in its own cacheable chunk
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      output: {
        manualChunks: { maplibre: ['maplibre-gl'], vendor: ['react', 'react-dom', 'framer-motion', 'd3'] },
      },
    },
  },
})
