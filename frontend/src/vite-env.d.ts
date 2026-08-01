/// <reference types="vite/client" />

// .env で差し替えられる環境変数の型。vite/client の ImportMetaEnv にマージされる
interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
