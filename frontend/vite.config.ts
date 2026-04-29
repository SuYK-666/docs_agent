import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0', // 允许局域网访问
    allowedHosts: true, // 👈 加上这一行！允许所有内网穿透的外部域名访问
    proxy: {
      // 将所有 /api 开头的请求代理到 Python 后端
      '/api': {
        target: 'http://127.0.0.1:1708', // <--- 如果你的 python 运行在 8000，请改这里
        changeOrigin: true,
      },
      // 将审批下发接口也代理过去
      '/approve_task': {
        target: 'http://127.0.0.1:1708', // <--- 同上
        changeOrigin: true,
      }
    }
  }
})
