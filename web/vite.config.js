import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  // history 路由下必须用绝对路径：/list 里再写 ./assets/... 会解析到错误位置
  base: '/',
  build: {
    outDir: 'dist',
    assetsInlineLimit: 0,
    chunkSizeWarningLimit: 2000,
  },
  server: {
    port: 5173,
    host: '127.0.0.1',
  },
})
