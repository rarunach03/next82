import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// The site is served from the root (https://next82.vercel.app).
export default defineConfig({
  base: '/',
  plugins: [react(), tailwindcss()],
})
