import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // ポートが埋まっていたら 5174 へずらさず、その場で失敗させる。
    // バックエンドの CORS 許可リスト（backend/app/main.py の CORS_ORIGINS）は
    // 5173 しか含まないため、黙ってずれると原因の分かりにくい CORS エラーになる。
    // 「Port 5173 is already in use」で落ちてくれたほうが切り分けが早い。
    strictPort: true,
  },
})
