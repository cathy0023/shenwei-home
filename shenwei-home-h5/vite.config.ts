import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  base: '/h5/',
  server: {
    port: 5275,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8200',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.test.{ts,tsx}'],
  },
});
