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


# 一覧から落とすモデル名の断片（2026-08-02）。
#
# models.list() の supported_actions では判別できない。TTS も画像生成も computer-use も
# generateContent を宣言しているのに、このアプリの使い方（テキストを渡してテキストを受け取る）
# では動かない。実測した失敗:
#   *-tts            -> 400 「response modalities (TEXT) is not supported」
#   *-image          -> 429 無料枠が無い
#   computer-use     -> 429 同上（専用ツールの指定も要る）
#   omni / robotics  -> 汎用の対話用ではない
# 名前による除外なので新しい系列が出れば取りこぼす。**最後の砦は保存時の実呼び出し検証**
# （verify_model）であって、この一覧ではない。ここは明らかな地雷を選択肢から消すだけ。
_NON_TEXT_FRAGMENTS = (
    "-image",
    "-tts",
    "computer-use",
    "robotics",
    "omni",
    "native-audio",
    "-live",
)


def _is_text_model(short_name: str) -> bool:
    """テキスト生成に使える見込みがあるモデル名か。"""
    return not any(frag in short_name for frag in _NON_TEXT_FRAGMENTS)


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

    **一覧に出る＝このアプリで使える、ではない。** ここを通っても無料枠が無ければ 429 になる
    （pro系は実際にそうなる）。選んだモデルが本当に使えるかは verify_model で確かめること。
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
            if short.startswith("gemini") and _is_text_model(short):
                names.append(short)
        return sorted(set(names))
    except Exception as e:  # SDKの例外型は環境差があるため広く捕捉して包み直す
        raise GeminiCallFailed(str(e)) from e


def describe_failure(err: Exception) -> str:
    """Gemini の失敗を、利用者が次に何をすればよいか分かる1文にする。

    SDK の例外文はJSONまるごとで数百文字あり、そのまま画面に出すと読まれない。
    原因の切り分けに要るのは、実測で出た次の3つの区別だけだった:
      429 -> そのキーにそのモデルの枠が無い（pro系や画像系で起きる）
      400 + response modalities -> テキストを返さないモデル（TTS・画像生成）
      400 + API key not valid   -> キーが違う
    どれにも当てはまらなければ原文の先頭だけを返す（握り潰すと調査できなくなるため）。
    """
    text = str(err)
    if "RESOURCE_EXHAUSTED" in text or text.startswith("429"):
        return "このAPIキーでは、このモデルの利用枠がありません。別のモデル（flash系）を選んでください"
    if "response modalities" in text:
        return "このモデルはテキストを返しません（音声や画像を生成するモデルです）"
    if "API key not valid" in text or "API_KEY_INVALID" in text:
        return "APIキーが正しくありません"
    return text.splitlines()[0][:200]


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


def verify_model(api_key: str, model: str) -> None:
    """このアプリの使い方でモデルが実際に使えるかを1回だけ呼んで確かめる。

    使えなければ GeminiCallFailed を送出する。

    実際に呼ぶ以外に確かめる方法が無い。models.list() は「テキストを返せるか」も
    「そのキーに枠があるか」も教えてくれず、どちらも呼んだ瞬間に初めて分かる。
    設定を保存する前にここを通すこと。壊れたモデル名がDBに入ると、以後 /reflection が
    毎回 fallback（model: null の定型文）になり、画面上は何も異常に見えなくなる。
    """
    generate(api_key, model, prompt="ping", system="「ok」とだけ返してください。")


def test_connection(api_key: str, model: str) -> str:
    """接続テスト。短い応答を1回だけ生成させる。"""
    res = generate(
        api_key,
        model,
        prompt="「接続できました」とだけ返してください。",
        system="あなたは疎通確認用の応答器です。指示された文字列だけを返してください。",
    )
    return res.text
