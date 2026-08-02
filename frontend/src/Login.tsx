// React 本体は参照していない（JSX は自動 import される）。
// 名前で import すると noUnusedLocals に触れてビルドが落ちる
import { useEffect, useRef } from "react";
import "./Login.css";
import { useGoogleLogin } from "@react-oauth/google";

interface LoginProps {
  onLoginSuccess?: (tokenResponse: any) => void;
}

export const Login = ({ onLoginSuccess }: LoginProps) => {
  const headerRef = useRef<HTMLElement | null>(null);
  const cardRef = useRef<HTMLDivElement | null>(null);
  const footerRef = useRef<HTMLElement | null>(null);

  // フェードインアニメーション
  useEffect(() => {
    const elements = [headerRef.current, cardRef.current, footerRef.current];

    elements.forEach((el, index) => {
      if (!el) return;
      el.style.opacity = "0";
      el.style.transform = "translateY(10px)";

      const timer = setTimeout(() => {
        el.style.transition = "all 800ms cubic-bezier(0.4, 0, 0.2, 1)";
        el.style.opacity = "1";
        el.style.transform = "translateY(0)";
      }, 150 * (index + 1));

      return () => clearTimeout(timer);
    });
  }, []);

  // Google ログイン処理
  const loginWithGoogle = useGoogleLogin({
    onSuccess: (tokenResponse) => {
      console.log("ログイン成功");
      if (onLoginSuccess) {
        onLoginSuccess(tokenResponse);
      }
    },
    onError: () => {
      console.log("ログイン失敗");
    },
  });

  return (
    <div className="login-container">
      <main className="login-main">
        {/* ヘッダー */}
        <header ref={headerRef} className="login-header">
          <h1 className="brand-title">
            {/* 雲アイコン（塗りつぶしタイプ） */}
            <svg
              className="brand-icon"
              viewBox="0 0 24 24"
              width="24"
              height="24"
              fill="#55534e"
            >
              <path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96z" />
            </svg>
            Atmosphere Studio
          </h1>
          <p className="brand-subtitle">
            頑張らない理由をプレゼントしてくれる、
            <br />
            省エネ提案アプリ
          </p>
        </header>

        {/* ログインカード */}
        <div ref={cardRef} className="login-card">
          <div className="card-icon-wrapper">
            {/* カード内の雲アイコン（線画タイプ） */}
            <svg
              viewBox="0 0 24 24"
              width="32"
              height="32"
              fill="none"
              stroke="#55534e"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z" />
            </svg>
          </div>

          <h2 className="card-title">今日は、空のせいにしましょう</h2>

          <p className="card-description">
            Google連携により、あなたの予定と気圧データを解析。
            <br />
            気象ストレスに合わせて、無理のない範囲で予定を「間引く」提案をします。
          </p>

          {/* ダークグレーGoogleログインボタン */}
          <button className="custom-google-btn" onClick={() => loginWithGoogle()}>
            <svg width="18" height="18" viewBox="0 0 24 24">
              <path
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                fill="#ffffff"
              />
              <path
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                fill="#ffffff"
              />
              <path
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
                fill="#ffffff"
              />
              <path
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                fill="#ffffff"
              />
            </svg>
            Googleでログイン
          </button>

          <p className="btn-annotation">
            ※カレンダー、タスク、メールの読み取り権限が必要です
          </p>
        </div>

        {/* フッター */}
        <footer ref={footerRef} className="login-footer">
          <div className="footer-links">
            <a href="#">プライバシーポリシー</a>
            <a href="#">利用規約</a>
          </div>
          <p className="footer-disclaimer">
            ※これは医学的アドバイスではありません。環境への気づきのためにご利用ください。
          </p>
          <p className="copyright">© ATMOSPHERE STUDIO</p>
        </footer>
      </main>
    </div>
  );
};

export default Login;