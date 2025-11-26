import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'

const projectRoot = fileURLToPath(new URL('.', import.meta.url))
const resolveModule = (pkg: string) => path.resolve(projectRoot, 'node_modules', pkg)

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      react: resolveModule('react'),
      'react-dom': resolveModule('react-dom'),
      'react-dom/client': resolveModule('react-dom/client'),
      'react/jsx-runtime': resolveModule('react/jsx-runtime'),
      'react/jsx-dev-runtime': resolveModule('react/jsx-dev-runtime'),
    },
    dedupe: ['react', 'react-dom', 'react-dom/client', 'react/jsx-runtime', 'react/jsx-dev-runtime'],
  },
  optimizeDeps: {
    include: ['react', 'react-dom', 'react-dom/client', 'react/jsx-runtime', 'react/jsx-dev-runtime'],
  },
})
