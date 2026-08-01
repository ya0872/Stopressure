"""Gemini API クライアント。

SDK（google-genai）が未インストールでもアプリ自体は起動できるよう、インポートを遅延させる。
設定画面で「SDKが入っていません」と案内するため、例外を握りつぶさず型で区別する。
"""
from __future__ import annotations

from dataclasses import dataclass


class GeminiSDKMissing(RuntimeError):
    """google-genai がインストールされていない。"""


class GeminiNotConfigured(RuntimeError):
    """APIキーが未設定。"""


class GeminiCallFailed(RuntimeError):
    """API呼び出しに失敗した（認証エラー・ネットワーク・レート制限など）。"""


@dataclass
class GenerateResult:
    text: str
    model: str


def sdk_installed() -> bool:
    """SDKが利用可能かを返す。"""
    try:
        import google.genai  # noqa: F401
    except ImportError:
        return False
    return True


def _client(api_key: str):
    """SDKクライアントを生成する。"""
    if not api_key:
        raise GeminiNotConfigured("Gemini APIキーが設定されていません")
    try:
        from google import genai
    except ImportError as e:
        raise GeminiSDKMissing(
            "google-genai が未インストールです。pip install -r requirements.txt を実行してください"
        ) from e
    return genai.Client(api_key=api_key)


def list_models(api_key: str) -> list[str]:
    """利用可能なモデル名の一覧を返す。

    モデル名は世代交代で変わるため、既定値を決め打ちせず実際のアカウントで使えるものを引く。
    """
    client = _client(api_key)
    try:
        names: list[str] = []
        for m in client.models.list():
            name = getattr(m, "name", "") or ""
            # "models/gemini-2.5-flash" 形式で返るため接頭辞を落とす
            short = name.split("/")[-1]
            # テキスト生成に使えないモデル（埋め込みなど）は除外する
            actions = getattr(m, "supported_actions", None) or []
            if actions and "generateContent" not in actions:
                continue
            if short.startswith("gemini"):
                names.append(short)
        return sorted(set(names))
    except Exception as e:  # SDKの例外型は環境差があるため広く捕捉して包み直す
        raise GeminiCallFailed(str(e)) from e


def generate(api_key: str, model: str, prompt: str, system: str | None = None) -> GenerateResult:
    """テキストを生成する。

    注意: この関数を呼んだ内容は Google へ送信される。版0.3 で夜の吐き出しも Gemini を
    使う構成に変わったが（docs/design.md §3.3）、自由文を渡してよいのは routers/reflection.py
    だけである。routers/generate.py は用途ホワイトリストで自由文を弾いており、
    「ユーザーの言葉が外部へ出る経路」を1箇所に閉じている。この構造を崩さないこと。
    """
    client = _client(api_key)
    try:
        from google.genai import types

        config = types.GenerateContentConfig(system_instruction=system) if system else None
        res = client.models.generate_content(model=model, contents=prompt, config=config)
        text = (getattr(res, "text", None) or "").strip()
        if not text:
            raise GeminiCallFailed("応答が空でした（安全フィルタで遮断された可能性があります）")
        return GenerateResult(text=text, model=model)
    except (GeminiSDKMissing, GeminiNotConfigured):
        raise
    except Exception as e:
        raise GeminiCallFailed(str(e)) from e


def test_connection(api_key: str, model: str) -> str:
    """接続テスト。短い応答を1回だけ生成させる。"""
    res = generate(
        api_key,
        model,
        prompt="「接続できました」とだけ返してください。",
        system="あなたは疎通確認用の応答器です。指示された文字列だけを返してください。",
    )
    return res.text
