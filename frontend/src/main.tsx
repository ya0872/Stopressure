import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { GoogleOAuthProvider } from '@react-oauth/google'
import './index.css'
import { Dashboard } from './Dashboard.tsx'
import { Login } from './Login.tsx'

const GOOGLE_CLIENT_ID = (import.meta.env.VITE_GOOGLE_CLIENT_ID as string) || '';

/**
 * ログイン画面を通過したことだけを覚えておくキー。
 *
 * **アクセストークンは保存しない。** Login.tsx が受け取るトークンはそのまま捨てており、
 * Google連携の実体はバックエンド側にある（PKCE + Fernet暗号化 / docs/design.md §7.2）。
 * ここに置くのは真偽値だけなので、最小権限の方針は変わらない。
 *
 * localStorage ではなく sessionStorage を使う。リロードでは保ちたいが、
 * タブを閉じたあとまでログイン済み扱いにはしたくないため。
 */
const LOGIN_FLAG_KEY = 'atmosphere.logged_in';

function MainApp() {
  // リロードのたびにログイン画面へ戻すと、再ログインで Dashboard がマウントし直され、
  // useGentleBlock のセッション内カウンタ（§4.8.1）が毎回 0 から始まる。
  // 「リロードすると制限が消える」経路のひとつがこれだった
  const [isLoggedIn, setIsLoggedIn] = useState(
    () => sessionStorage.getItem(LOGIN_FLAG_KEY) === '1',
  );

  const handleLoginSuccess = () => {
    sessionStorage.setItem(LOGIN_FLAG_KEY, '1');
    setIsLoggedIn(true);
  };

  return isLoggedIn ? (
    <Dashboard />
  ) : (
    <Login onLoginSuccess={handleLoginSuccess} />
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      <MainApp />
    </GoogleOAuthProvider>
  </StrictMode>,
)

