"""Gemini設定APIの検証。

実際のGemini APIは呼ばず、gemini モジュールを差し替えて挙動だけを確認する。

このファイルが守っているのは1点:
  **使えない設定は保存させない。** 使えないモデル名がDBに入ると /reflection は
  毎回 fallback（200 + model: null の定型文）を返し、UIは正常に見えたまま Gemini を
  一度も通らなくなる。原因の分からない「動かない」がここから生まれる。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import settings_store as store
from app.main import app
from app.services import gemini

client = TestClient(app)


@pytest.fixture
def with_key(monkeypatch):
    """APIキーが登録済みの状態にする。"""
    store.set_secret(store.KEY_GEMINI_API, "dummy-key-1234567890")
    monkeypatch.setattr(gemini, "sdk_installed", lambda: True)


@pytest.fixture
def model_ok(monkeypatch):
    """どのモデルでも生成できる状態にする。"""
    monkeypatch.setattr(gemini, "verify_model", lambda key, model: None)


@pytest.fixture
def model_ng(monkeypatch):
    """どのモデルでも生成に失敗する状態にする。"""
    def boom(key, model):
        raise gemini.GeminiCallFailed("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(gemini, "verify_model", boom)


def test_saves_model_when_it_works(with_key, model_ok):
    """検証を通ったモデルは保存される。"""
    res = client.put("/api/v1/settings/gemini", json={"model": "gemini-2.5-flash"})
    assert res.status_code == 200
    assert res.json()["model"] == "gemini-2.5-flash"
    assert store.resolve_gemini_model() == "gemini-2.5-flash"


def test_rejects_model_that_cannot_generate(with_key, model_ok, model_ng):
    """生成できないモデルは400で弾き、**保存済みの設定を変えない**。

    ここが通ってしまうと、以後の /reflection が黙って定型文だけを返すようになる。
    """
    store.set_plain(store.KEY_GEMINI_MODEL, "gemini-2.5-flash")

    res = client.put("/api/v1/settings/gemini", json={"model": "gemini-3-pro-image"})
    assert res.status_code == 400
    assert "gemini-3-pro-image" in res.json()["detail"]
    # 壊れた値でDBを上書きしていないこと
    assert store.resolve_gemini_model() == "gemini-2.5-flash"


def test_rejects_api_key_that_cannot_generate(with_key, model_ng):
    """キーの保存も同じ扱い。使えないキーは保存しない。"""
    store.set_secret(store.KEY_GEMINI_API, "old-key-1234567890")

    res = client.put("/api/v1/settings/gemini", json={"api_key": "new-key-1234567890"})
    assert res.status_code == 400
    assert store.get_secret(store.KEY_GEMINI_API) == "old-key-1234567890"


def test_saves_model_without_key_and_skips_verification(monkeypatch):
    """キー未登録なら検証しようがないので、モデルだけ先に決められる。"""
    def must_not_be_called(key, model):
        raise AssertionError("キーが無いのに検証を呼んでいる")

    monkeypatch.setattr(gemini, "verify_model", must_not_be_called)
    monkeypatch.setattr(store, "resolve_gemini_api_key", lambda: None)

    res = client.put("/api/v1/settings/gemini", json={"model": "gemini-2.5-flash"})
    assert res.status_code == 200
    assert store.resolve_gemini_model() == "gemini-2.5-flash"


def test_rejects_blank_model(with_key, model_ok):
    """空白だけのモデル名は弾く。strip すると空になり、既定値に化けるため。"""
    res = client.put("/api/v1/settings/gemini", json={"model": "   "})
    assert res.status_code == 400


def test_error_message_is_short_and_actionable(with_key, monkeypatch):
    """画面に出す文言はSDKの例外文そのままにしない。

    生の例外はJSONまるごとで数百文字あり、そのまま出しても読まれない。
    """
    long_error = (
        "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your "
        "current quota, please check your plan and billing details. " + "x" * 500 + "'}}"
    )

    def boom(key, model):
        raise gemini.GeminiCallFailed(long_error)

    monkeypatch.setattr(gemini, "verify_model", boom)
    res = client.put("/api/v1/settings/gemini", json={"model": "gemini-2.5-pro"})
    detail = res.json()["detail"]
    assert res.status_code == 400
    assert len(detail) < 200
    assert "利用枠がありません" in detail


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("429 RESOURCE_EXHAUSTED. {...}", "利用枠がありません"),
        ("400 INVALID_ARGUMENT. response modalities (TEXT) is not supported", "テキストを返しません"),
        ("400 INVALID_ARGUMENT. API key not valid", "APIキーが正しくありません"),
    ],
)
def test_describe_failure_classifies_known_causes(raw, expected):
    """実測した3つの失敗を区別できること。"""
    assert expected in gemini.describe_failure(gemini.GeminiCallFailed(raw))


def test_describe_failure_keeps_unknown_errors():
    """知らない失敗は握り潰さず原文の先頭を返す。調べる手がかりを消さないため。"""
    assert "something odd" in gemini.describe_failure(gemini.GeminiCallFailed("something odd"))


def test_list_models_drops_non_text_models(monkeypatch):
    """一覧はテキスト生成に使えないモデルを落とす。

    TTS も画像も computer-use も supported_actions に generateContent を載せてくるので、
    そこだけでは判別できない。選択肢に出すと保存されて壊れるため名前で落とす。
    """
    class FakeModel:
        def __init__(self, name):
            self.name = f"models/{name}"
            self.supported_actions = ["generateContent", "countTokens"]

    class FakeClient:
        class models:
            @staticmethod
            def list():
                return [
                    FakeModel(n)
                    for n in (
                        "gemini-2.5-flash",
                        "gemini-3.6-flash",
                        "gemini-3-pro-image",
                        "gemini-2.5-flash-preview-tts",
                        "gemini-2.5-computer-use-preview-10-2025",
                        "gemini-omni-flash-preview",
                        "gemini-robotics-er-2-preview",
                        "gemini-2.5-flash-native-audio-latest",
                        "gemma-4-31b-it",
                    )
                ]

    monkeypatch.setattr(gemini, "_client", lambda key: FakeClient())
    assert gemini.list_models("dummy") == ["gemini-2.5-flash", "gemini-3.6-flash"]
