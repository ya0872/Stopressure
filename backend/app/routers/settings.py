"""設定API。

APIキーは書き込み専用として扱う。保存はできるが、平文で読み出す経路は用意しない。
画面に返すのはマスク済みの文字列だけ。
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from .. import settings_store as store
from ..crypto import mask
from ..services import gemini, google_client, google_oauth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

# Google の client_id は「数字-英小数字.apps.googleusercontent.com」の形をとる。
# 手入力で空白や記号が混入すると、Googleは認可の入口で 401 invalid_client を返し、
# 「クライアントが見つからない」としか言わないため原因が分かりにくい。
# 保存の時点で弾いて、どこが変なのかをこちら側で伝える
_CLIENT_ID_RE = re.compile(r"^\d+-[a-z0-9]+\.apps\.googleusercontent\.com$")


class GeminiStatus(BaseModel):
    """設定画面に表示する状態。平文キーは含めない。"""
    configured: bool = Field(description="APIキーが登録済みか")
    masked_key: str | None = Field(default=None, description="マスク済みキー（表示確認用）")
    source: str | None = Field(default=None, description="キーの取得元: settings | env")
    model: str = Field(description="使用するモデル名")
    sdk_installed: bool = Field(description="google-genai が利用可能か")


class GeminiUpdate(BaseModel):
    # api_key を省略した場合は既存のキーを維持する（モデルだけ変えたい場合に使う）
    api_key: str | None = Field(default=None, min_length=10, max_length=400)
    model: str | None = Field(default=None, min_length=1, max_length=100)


class TestResult(BaseModel):
    ok: bool
    message: str


@router.get("/gemini", response_model=GeminiStatus)
def get_gemini_status() -> GeminiStatus:
    """現在の設定状態を返す。"""
    from_settings = store.get_secret(store.KEY_GEMINI_API)
    key = store.resolve_gemini_api_key()
    return GeminiStatus(
        configured=bool(key),
        masked_key=mask(key) if key else None,
        source=("settings" if from_settings else "env") if key else None,
        model=store.resolve_gemini_model(),
        sdk_installed=gemini.sdk_installed(),
    )


@router.put("/gemini", response_model=GeminiStatus)
def update_gemini(body: GeminiUpdate) -> GeminiStatus:
    """APIキーとモデルを保存する。

    保存する前に、その (キー, モデル) の組で実際に1回生成できることを確かめる。
    確かめずに書くと、使えないモデル名がそのままDBに残る。そうなると /reflection は
    毎回 fallback（model: null の定型文）を返し、UIは正常に見えたまま Gemini を
    一度も通らなくなる。設定画面で「保存しました」と出たものは動く、を守るための検証。
    """
    if body.api_key is None and body.model is None:
        raise HTTPException(status_code=400, detail="api_key か model のいずれかを指定してください")

    # 前後の空白は貼り付け事故が多いので落とす
    api_key = body.api_key.strip() if body.api_key is not None else None
    model = body.model.strip() if body.model is not None else None
    if body.model is not None and not model:
        raise HTTPException(status_code=400, detail="モデル名が空です")

    # 検証には「保存後に有効になる値」を使う。省略された側は現在値を引き継ぐ
    effective_key = api_key or store.resolve_gemini_api_key()
    effective_model = model or store.resolve_gemini_model()

    # キーが無い状態でモデルだけ先に決めておく使い方は許す（呼びようがないため検証も省く）
    if effective_key:
        try:
            gemini.verify_model(effective_key, effective_model)
        except gemini.GeminiSDKMissing as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        except gemini.GeminiCallFailed as e:
            # 400 にするのは、直すべきなのが送った値（キーかモデル名）だから。
            # 502 にすると「Gemini側の一時障害」と読めてしまい、再試行を誘う。
            # 画面には要約だけを出し、原文はログへ回す（SDKの例外文はJSONまるごとで長い）
            logger.warning("設定の検証に失敗しました (model=%s)", effective_model, exc_info=True)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{effective_model} は使えないため保存しませんでした。"
                    f"{gemini.describe_failure(e)}"
                ),
            ) from e

    if api_key is not None:
        store.set_secret(store.KEY_GEMINI_API, api_key)
    if model is not None:
        store.set_plain(store.KEY_GEMINI_MODEL, model)

    return get_gemini_status()


@router.delete("/gemini", response_model=GeminiStatus)
def delete_gemini_key() -> GeminiStatus:
    """登録済みのAPIキーを削除する。モデル設定は残す。"""
    store.delete(store.KEY_GEMINI_API)
    return get_gemini_status()


@router.get("/gemini/models", response_model=list[str])
def get_available_models() -> list[str]:
    """このアカウントで使えるモデル名の一覧を返す。"""
    key = store.resolve_gemini_api_key()
    if not key:
        raise HTTPException(status_code=409, detail="APIキーが未設定です")
    try:
        return gemini.list_models(key)
    except gemini.GeminiSDKMissing as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except gemini.GeminiCallFailed as e:
        raise HTTPException(status_code=502, detail=f"モデル一覧の取得に失敗しました: {e}") from e


class GoogleStatus(BaseModel):
    """Google連携の状態。client_secret もトークンも含めない。"""
    configured: bool = Field(description="OAuthクライアントが登録済みか")
    linked: bool = Field(description="Googleアカウントと連携済みか")
    client_id: str | None = Field(default=None, description="client_id は認可URLに載るため平文で返す")
    scopes: list[str] = Field(description="要求する権限。すべて読み取り専用")
    linked_at: str | None = Field(default=None, description="連携した日時(UTC)")
    use_context: bool = Field(description="カレンダー等を体力予算に反映するか")
    login_url: str = Field(description="連携を開始するURL")


class GoogleUpdate(BaseModel):
    # 片方だけの更新を許す。既存値は維持される
    client_id: str | None = Field(
        default=None, min_length=10, max_length=400,
        description="例: 123456789012-abcdefghijklmnop.apps.googleusercontent.com",
    )
    client_secret: str | None = Field(default=None, min_length=6, max_length=400)
    use_context: bool | None = Field(
        default=None,
        description="false にすると連携は保ったまま体力予算への反映だけを止める（§7.2）",
    )

    @field_validator("client_id")
    @classmethod
    def _validate_client_id(cls, v: str | None) -> str | None:
        """形式を検査する。手入力による取り違えを保存前に止める。"""
        if v is None:
            return v
        v = v.strip()
        if _CLIENT_ID_RE.fullmatch(v):
            return v

        # 何が悪いのかを具体的に指す。「形式が不正」だけでは直しようがない
        problems: list[str] = []
        if any(c.isspace() for c in v):
            problems.append("空白が含まれています")
        bad = sorted({c for c in v if not (c.isascii() and (c.isalnum() or c in "-."))})
        if bad:
            problems.append("使えない文字が含まれています: " + " ".join(bad))
        if not v.endswith(".apps.googleusercontent.com"):
            problems.append("末尾が .apps.googleusercontent.com ではありません")
        if any(c.isupper() for c in v.split(".apps.")[0]):
            problems.append("大文字が含まれています")
        if not problems:
            problems.append("「数字-英数字.apps.googleusercontent.com」の形になっていません")

        raise ValueError(
            "client_id の形式が正しくありません（" + " / ".join(problems) + "）。"
            "Google Cloud Console のクライアントID横にあるコピーボタンで取得して、"
            "手入力せずに貼り付けてください"
        )

    @field_validator("client_secret")
    @classmethod
    def _validate_client_secret(cls, v: str | None) -> str | None:
        """シークレットに空白は入らない。貼り付け事故を保存前に止める。"""
        if v is None:
            return v
        v = v.strip()
        if any(c.isspace() for c in v):
            raise ValueError(
                "client_secret に空白が含まれています。"
                "コピーボタンで取得して、手入力せずに貼り付けてください"
            )
        return v


def _google_status() -> GoogleStatus:
    s = google_oauth.status()
    client_id, _ = store.resolve_google_client()
    return GoogleStatus(
        configured=s.configured,
        linked=s.linked,
        client_id=client_id,
        scopes=s.scopes,
        linked_at=s.linked_at,
        use_context=s.use_context,
        login_url="/api/v1/auth/google/login",
    )


@router.get("/google", response_model=GoogleStatus)
def get_google_status() -> GoogleStatus:
    """Google連携の状態を返す。"""
    return _google_status()


@router.put("/google", response_model=GoogleStatus)
def update_google(body: GoogleUpdate) -> GoogleStatus:
    """OAuthクライアントと反映フラグを保存する。"""
    if body.client_id is None and body.client_secret is None and body.use_context is None:
        raise HTTPException(
            status_code=400, detail="client_id / client_secret / use_context のいずれかを指定してください"
        )

    if body.client_id is not None:
        store.set_plain(store.KEY_GOOGLE_CLIENT_ID, body.client_id.strip())
    if body.client_secret is not None:
        store.set_secret(store.KEY_GOOGLE_CLIENT_SECRET, body.client_secret.strip())
    if body.use_context is not None:
        store.set_plain(store.KEY_GOOGLE_USE_CONTEXT, "1" if body.use_context else "0")

    # 設定を変えたのに古い取得結果が5分残るのは不可解なので、都度捨てる
    google_client.clear_context_cache()
    return _google_status()


@router.post("/google/test", response_model=TestResult)
def test_google_client() -> TestResult:
    """client_id と client_secret の組み合わせを検証する。

    認可画面を通さずに確かめられる。シークレットの誤りは、これが無いと
    「ログインは通るのにトークン交換で落ちる」という分かりにくい形でしか出ない。
    """
    try:
        ok, message = google_oauth.verify_client()
        return TestResult(ok=ok, message=message)
    except google_oauth.GoogleNotConfigured as e:
        return TestResult(ok=False, message=str(e))
    except google_oauth.GoogleAuthFailed as e:
        return TestResult(ok=False, message=str(e))


@router.delete("/google", response_model=GoogleStatus)
def unlink_google() -> GoogleStatus:
    """連携を解除する。保存済みトークンを削除する。

    Google側の許可はこの操作では取り消されない。完全に断つ場合は
    https://myaccount.google.com/permissions からも削除する必要がある。
    """
    google_oauth.unlink()
    google_client.clear_context_cache()
    return _google_status()


@router.post("/gemini/test", response_model=TestResult)
def test_gemini() -> TestResult:
    """疎通確認。短い生成を1回だけ試す。"""
    key = store.resolve_gemini_api_key()
    if not key:
        return TestResult(ok=False, message="APIキーが未設定です")
    try:
        text = gemini.test_connection(key, store.resolve_gemini_model())
        return TestResult(ok=True, message=text)
    except gemini.GeminiSDKMissing as e:
        return TestResult(ok=False, message=str(e))
    except gemini.GeminiCallFailed as e:
        # ネットワーク環境によっては接続自体が失敗しうるため、原因を見せる。
        # 原文はログにあるので、画面には要約だけを出す
        logger.warning("疎通テストに失敗しました", exc_info=True)
        return TestResult(ok=False, message=f"呼び出しに失敗しました: {gemini.describe_failure(e)}")
