import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

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
  build: {
    rollupOptions: {
      // マルチページ構成。開発サーバーは root 直下のHTMLを自動で拾うが、
      // ビルド時は明示しないと index.html しか出力されない。
      //   index.html   → 製品画面（Dashboard）
      //   console.html → 設定・接続状態コンソール（src/console/）
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        console: fileURLToPath(new URL('./console.html', import.meta.url)),
      },
    },
  },
})
