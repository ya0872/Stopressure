import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { GoogleOAuthProvider } from '@react-oauth/google'
import './index.css'
import { Dashboard } from './Dashboard.tsx'
import { Login } from './Login.tsx'

const GOOGLE_CLIENT_ID = (import.meta.env.VITE_GOOGLE_CLIENT_ID as string) || '';

function MainApp() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  return isLoggedIn ? (
    <Dashboard />
  ) : (
    <Login onLoginSuccess={() => setIsLoggedIn(true)} />
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      <MainApp />
    </GoogleOAuthProvider>
  </StrictMode>,
)

