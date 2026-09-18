import { defineConfig } from 'vite';
export default defineConfig({
  base: './',
  build: { target: 'esnext' },
  worker: { format: 'es' },
  optimizeDeps: { exclude: ['@gorules/zen-engine-wasm32-wasi'] },
  server: { headers: { 'Cross-Origin-Opener-Policy': 'same-origin', 'Cross-Origin-Embedder-Policy': 'require-corp' } },
  preview: { headers: { 'Cross-Origin-Opener-Policy': 'same-origin', 'Cross-Origin-Embedder-Policy': 'require-corp' } },
});
