/**
 * コンソールのエントリポイント。console.html から読み込まれる。
 * 製品画面（src/main.tsx → Dashboard）とは別のバンドルになる。
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ConsoleApp } from './ConsoleApp';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConsoleApp />
  </StrictMode>,
);
