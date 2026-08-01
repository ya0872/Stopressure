"""Google OAuth の認可フロー（docs/design.md §5 / §7.2）。

/login でGoogleの同意画面へ送り、/callback で認可コードを受け取ってトークンを保存する。
/callback はブラウザが直接開くため、JSONではなく最小限のHTMLを返す。
"""
from __future__ import annotations

import logging
import os
from html import escape

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..services import google_oauth
from ..services.google_oauth import GoogleAuthFailed, GoogleNotConfigured

router = APIRouter(prefix="/auth/google", tags=["auth"])
logger = logging.getLogger(__name__)

# 認可後に戻る画面。静的サーバーの位置は環境で変わりうるので環境変数で上書きできる
SETTINGS_URL = os.getenv("FRONTEND_URL", "http://localhost:8765").rstrip("/") + "/settings.html"


def _redirect_uri(request: Request) -> str:
    """このサーバー自身のコールバックURLを組み立てる。

    Google Cloud Console に登録したURLと完全一致する必要がある。ポートを変えて起動した
    場合にずれないよう、リクエストのホストから組み立てる。
    """
    return str(request.base_url).rstrip("/") + google_oauth.REDIRECT_PATH


def _page(title: str, message: str, *, ok: bool, hint: str = "") -> HTMLResponse:
    """結果表示用の最小ページ。外部リソースを読み込まない。

    設定画面へ戻る導線を必ず置く。ここが行き止まりだと、失敗したときに
    利用者はタブを閉じて手で開き直すしかなくなる。
    """
    color = "#5b8266" if ok else "#8f5a5a"
    hint_html = (
        f'<p style="margin:1rem 0 0;font-size:.8rem;opacity:.6;line-height:1.9">{escape(hint)}</p>'
        if hint else ""
    )
    body = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title></head>
<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
             background:#1b1c1e;color:#e6e4e1;font-family:system-ui,sans-serif">
  <main style="max-width:32rem;padding:2rem;line-height:1.9">
    <h1 style="font-size:1.1rem;font-weight:600;color:{color};margin:0 0 .8rem">{escape(title)}</h1>
    <p style="margin:0;font-size:.9rem;opacity:.85">{escape(message)}</p>
    {hint_html}
    <p style="margin:1.8rem 0 0">
      <a href="{escape(SETTINGS_URL)}"
         style="display:inline-block;padding:.5rem 1rem;border:1px solid #3a3d45;border-radius:4px;
                color:#e6e4e1;text-decoration:none;font-size:.8rem;letter-spacing:.06em">
        設定画面に戻る
      </a>
    </p>
  </main>
</body></html>"""
    return HTMLResponse(body, status_code=200 if ok else 400)


@router.get("/login")
def login(request: Request) -> RedirectResponse:
    """Googleの認可画面へリダイレクトする。"""
    try:
        url = google_oauth.build_authorization_url(_redirect_uri(request))
    except GoogleNotConfigured as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return RedirectResponse(url, status_code=302)


@router.get("/callback", response_class=HTMLResponse)
def callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> HTMLResponse:
    """認可コードを受け取り、トークンを保存する。"""
    if error:
        # 同意画面で拒否した場合など。エラーにはせず、状況をそのまま伝える
        return _page("連携しませんでした", f"Googleから次の応答がありました: {error}", ok=False)

    if not code or not state:
        return _page("連携できませんでした", "認可コードが受け取れませんでした。", ok=False)

    try:
        google_oauth.exchange_code(code, state, _redirect_uri(request))
    except (GoogleAuthFailed, GoogleNotConfigured) as e:
        # 原因の切り分けにサーバーログを使えるようにする。画面には出せない詳細も残す
        logger.warning("Google連携に失敗: %s", e, exc_info=True)

        text = str(e)
        if "invalid_client" in text:
            hint = (
                "この画面に来る前に client_id / client_secret を変更した場合、"
                "認可を始めたときのクライアントと、いま保存されているクライアントが食い違います。"
                "設定画面で「ID と シークレットを検証」が通ることを確かめてから、"
                "同じタブで最初からやり直してください。"
            )
        elif "state" in text:
            hint = (
                "バックエンドを再起動すると、発行済みのstateは失われます。"
                "設定画面から改めて「Googleと連携する」を押してください。"
            )
        else:
            hint = "設定画面の「ID と シークレットを検証」で、資格情報が正しいかを先に確認できます。"

        return _page("連携できませんでした", text, ok=False, hint=hint)

    return _page(
        "連携しました",
        "カレンダーの拘束時間、ToDoの件数、未読の重要メール件数を、"
        "今日の体力予算に反映します。メールの件名や本文は取得しません。",
        ok=True,
    )
