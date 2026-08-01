"""設定API。

APIキーは書き込み専用として扱う。保存はできるが、平文で読み出す経路は用意しない。
画面に返すのはマスク済みの文字列だけ。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import settings_store as store
from ..crypto import mask
from ..services import gemini

router = APIRouter(prefix="/settings", tags=["settings"])


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
    """APIキーとモデルを保存する。"""
    if body.api_key is None and body.model is None:
        raise HTTPException(status_code=400, detail="api_key か model のいずれかを指定してください")

    if body.api_key is not None:
        # 前後の空白は貼り付け事故が多いので落とす
        store.set_secret(store.KEY_GEMINI_API, body.api_key.strip())
    if body.model is not None:
        store.set_plain(store.KEY_GEMINI_MODEL, body.model.strip())

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
        # 学内プロキシ環境では接続自体が失敗しうるため、原因をそのまま見せる
        return TestResult(ok=False, message=f"呼び出しに失敗しました: {e}")
