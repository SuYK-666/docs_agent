import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
  ],
  server: {
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