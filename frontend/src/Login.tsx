
import "./Login.css";
// Google login Button
import { GoogleLogin } from "@react-oauth/google";
//import { jwtDecode } from "jwt-decode";
import type { CredentialResponse } from "@react-oauth/google";

interface LoginProps {
  onLoginSuccess?: (credentialResponse: CredentialResponse) => void;
}

export const Login = ({ onLoginSuccess }: LoginProps) => {
    /**ログイン成功時処理 */
    const handleLoginSuccess = (credentialResponse: CredentialResponse) => {
        if (!credentialResponse.credential) {
            throw new Error("credentialResponse.credential is undefined");
        }
        console.log("ログイン成功:");
        if (onLoginSuccess) {
            onLoginSuccess(credentialResponse);
        }
    };

    /**ログイン失敗時処理 */
    const handleLoginError = () => {
        console.log("ログイン失敗");
        throw new Error("ログイン失敗");
    };
  return (
    <div>
      <h1>Login</h1>
      <GoogleLogin onSuccess={handleLoginSuccess} onError={handleLoginError} />
    </div>
  );
};
export default Login;