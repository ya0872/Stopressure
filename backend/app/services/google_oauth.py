"""Google OAuth 2.0 認可コードフロー（docs/design.md §7.2）。

アプリ本体はローカル動作だが、Google APIの利用には Google Cloud Console での
プロジェクト作成とOAuthクライアント登録が必須で、回避手段は存在しない。

スコープの選定方針:
    必要最小限に絞る。特に Gmail は本文アクセス権（gmail.readonly）を要求しない。
    要対応メール「数」から精神的負荷を推定するのが目的で、件名も本文も使わないため。
    審査リスクと、利用者の心理的抵抗の両方を下げるための判断（§7.2）。

    実際に呼ぶのは users.labels.get だけなので、さらに狭い gmail.labels でも足りる。
    設計書が gmail.metadata を明記しているためそちらに合わせてあるが、
    メールの内容を一切使わない方針を貫くなら gmail.labels へ狭めてよい。
"""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass

from .. import oauth_store, settings_store as store

# 認可コードフローで要求するスコープ。すべて読み取り専用
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",   # F-05 拘束時間
    "https://www.googleapis.com/auth/gmail.metadata",      # F-06 要対応メール数（本文は取得しない）
    "https://www.googleapis.com/auth/tasks.readonly",      # F-18 ToDo件数
]

# 認可後の戻り先。Google Cloud Console 側にも同じURLを登録しておくこと
REDIRECT_PATH = "/api/v1/auth/google/callback"
DEFAULT_REDIRECT_URI = f"http://localhost:8000{REDIRECT_PATH}"

# 発行済みで未使用の state → PKCE の code_verifier。
#
# state はCSRF対策。code_verifier は google-auth-oauthlib が認可URL生成時に自動生成し、
# その SHA256 を code_challenge としてGoogleへ送る。トークン交換では元の値を提示する必要があり、
# 保持し忘れると (invalid_grant) Missing code verifier で必ず失敗する。
# Flow を作り直すと verifier も作り直されるため、認可を始めた時点の値をここに預けておく。
#
# 単一ユーザーのローカル運用のためメモリで足りる（再起動すると認可し直しになるが、
# 認可は数分で終わる操作なので許容する）。
_pending_states: dict[str, str] = {}

# 認可を始めたまま完了しなかった分が溜まらないよう上限を設ける
_MAX_PENDING = 20

# oauthlib は既定で https 以外のリダイレクトURIを拒否する。ここでのリダイレクト先は
# 自分自身（localhost）で、通信がマシンの外に出ないため無効化してよい
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
# Google は要求と異なる順序・粒度でスコープを返すことがあり、既定だと例外になる
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


class GoogleNotConfigured(RuntimeError):
    """OAuthクライアント（client_id / client_secret）が未登録。"""


class GoogleNotLinked(RuntimeError):
    """まだGoogleアカウントと連携していない。"""


class GoogleAuthFailed(RuntimeError):
    """認可またはトークン更新に失敗した。"""


@dataclass(frozen=True)
class LinkStatus:
    configured: bool          # client_id / secret が登録済みか
    linked: bool              # トークンを保持しているか
    scopes: list[str]
    linked_at: str | None
    use_context: bool         # 体力予算への反映が有効か


def _client_config(redirect_uri: str) -> dict:
    """google-auth-oauthlib が要求する client_secrets 形式を組み立てる。

    JSONファイルを置かせずDBから組み立てるのは、秘密情報の置き場を
    「暗号化されたDB」1箇所に揃えるため。
    """
    client_id, client_secret = store.resolve_google_client()
    if not client_id or not client_secret:
        raise GoogleNotConfigured(
            "Google OAuth クライアントが未登録です。"
            "Google Cloud Console で作成し、設定から client_id / client_secret を登録してください"
        )
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }


def _flow(redirect_uri: str, state: str | None = None):
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(_client_config(redirect_uri), scopes=SCOPES, state=state)
    flow.redirect_uri = redirect_uri
    return flow


def build_authorization_url(redirect_uri: str = DEFAULT_REDIRECT_URI) -> str:
    """認可画面のURLを組み立てる。"""
    state = secrets.token_urlsafe(24)
    flow = _flow(redirect_uri, state=state)
    url, _ = flow.authorization_url(
        # refresh_token を得るために必要。これが無いと1時間で切れて連携し直しになる
        access_type="offline",
        # 2回目以降も refresh_token を確実に受け取るため、毎回同意画面を出す
        prompt="consent",
        include_granted_scopes="true",
    )

    # 古い未完了分から捨てる。認可を開いて放置した分が無限に溜まらないようにする
    while len(_pending_states) >= _MAX_PENDING:
        _pending_states.pop(next(iter(_pending_states)))

    # authorization_url() の呼び出しで code_verifier が確定する。この順序を崩さないこと
    _pending_states[state] = flow.code_verifier
    return url


def exchange_code(code: str, state: str, redirect_uri: str = DEFAULT_REDIRECT_URI) -> None:
    """認可コードをトークンに交換して保存する。"""
    if state not in _pending_states:
        # 自分が発行していない state で来たリクエストは受け付けない
        raise GoogleAuthFailed("stateが一致しません。認可をやり直してください")
    code_verifier = _pending_states.pop(state)

    flow = _flow(redirect_uri, state=state)
    # Flow を作り直すと code_verifier も作り直される。認可時の値に差し替えないと
    # Googleは (invalid_grant) Missing code verifier を返す
    flow.code_verifier = code_verifier

    try:
        flow.fetch_token(code=code)
    except Exception as e:  # oauthlib/requests の例外型は環境差があるため広く捕捉する
        raise GoogleAuthFailed(f"トークンの取得に失敗しました: {e}") from e

    creds = flow.credentials
    expires_at = creds.expiry.isoformat() if creds.expiry else None
    oauth_store.save(oauth_store.PROVIDER_GOOGLE, creds.to_json(), expires_at)


def load_credentials():
    """保存済みトークンから Credentials を復元する。期限切れなら更新して保存し直す。"""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    stored = oauth_store.load(oauth_store.PROVIDER_GOOGLE)
    if stored is None:
        raise GoogleNotLinked("Googleアカウントと連携していません")

    try:
        creds = Credentials.from_authorized_user_info(json.loads(stored.payload), SCOPES)
    except (ValueError, KeyError) as e:
        raise GoogleAuthFailed(f"保存済みトークンを読めませんでした: {e}") from e

    if creds.valid:
        return creds

    if not creds.refresh_token:
        # 同意画面で offline アクセスが得られなかった場合。連携し直すしかない
        raise GoogleNotLinked("トークンの有効期限が切れています。連携し直してください")

    try:
        creds.refresh(Request())
    except Exception as e:
        raise GoogleAuthFailed(f"トークンの更新に失敗しました: {e}") from e

    oauth_store.save(
        oauth_store.PROVIDER_GOOGLE,
        creds.to_json(),
        creds.expiry.isoformat() if creds.expiry else None,
    )
    return creds


def verify_client(redirect_uri: str = DEFAULT_REDIRECT_URI) -> tuple[bool, str]:
    """client_id と client_secret の組み合わせが正しいかを確かめる。

    仕組み: わざと無効な認可コードでトークン交換を試みる。Googleの応答は
        - シークレットが違う      → invalid_client
        - シークレットは正しい    → invalid_grant（コードが無効なだけ）
    と分かれるため、この差でシークレットの正否だけを判定できる。認可画面を通す必要がない。

    これが無いと、シークレットの誤りは「ログインは通るのにトークン交換で落ちる」という
    分かりにくい形でしか表面化しない（実際にそれで詰まった）。
    """
    import httpx

    client_id, client_secret = store.resolve_google_client()
    if not client_id or not client_secret:
        raise GoogleNotConfigured("client_id / client_secret が未登録です")

    try:
        res = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "authorization_code",
                # 通るはずのないダミー。ここが原因で必ず失敗するのが前提
                "code": "invalid-code-used-only-to-verify-the-client-secret",
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
            timeout=20.0,
        )
        payload = res.json()
    except Exception as e:
        # 環境側が原因のことが多い
        raise GoogleAuthFailed(f"Googleに接続できませんでした: {e}") from e

    error = payload.get("error", "")
    desc = payload.get("error_description", "")

    if error == "invalid_grant":
        # コードが無効という応答＝client_id と secret の組み合わせは受理された
        return True, "client_id と client_secret の組み合わせは正しいです。"
    if error == "invalid_client":
        return False, (
            "client_secret がこの client_id のものと一致しません。"
            "別のクライアント（または別プロジェクト）のシークレットを貼っていないか確認してください。"
            "Cloud Console では既存のシークレットを再表示できないため、"
            "対象のクライアントで新しいシークレットを追加し、作成直後にコピーしてください。"
        )
    if error:
        return False, f"想定外の応答です: {error} — {desc}"
    return False, "想定外の応答です（エラーが返りませんでした）"


def unlink() -> None:
    """連携を解除する。保存済みトークンを消すだけで、Google側の取り消しは行わない。

    Google側からも取り消したい場合は、利用者自身がアカウント設定から削除する必要がある
    （その旨をレスポンスで案内する）。
    """
    oauth_store.delete(oauth_store.PROVIDER_GOOGLE)


def status() -> LinkStatus:
    """連携状態を返す。トークンの中身は一切含めない。"""
    client_id, client_secret = store.resolve_google_client()
    stored = oauth_store.load(oauth_store.PROVIDER_GOOGLE)
    return LinkStatus(
        configured=bool(client_id and client_secret),
        linked=stored is not None,
        scopes=SCOPES,
        linked_at=stored.updated_at if stored else None,
        use_context=store.google_context_enabled(),
    )
