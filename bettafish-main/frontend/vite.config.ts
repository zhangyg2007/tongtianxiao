import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// 开发模式下 /api 代理到 Flask（app.py，默认 5000 端口）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
});
