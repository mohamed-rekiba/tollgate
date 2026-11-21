import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// The site is served at https://tollgate-ai.github.io/.
export default defineConfig({
  base: '/',
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // The diagrams live in the repository's docs, drawn by the diagram skill.
      '@diagrams': fileURLToPath(new URL('../docs/diagrams', import.meta.url)),
    },
  },
  server: { fs: { allow: ['..'] } },
})
