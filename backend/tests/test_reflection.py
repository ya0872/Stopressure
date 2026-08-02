"""吐き出しエンドポイントの検証。

実際のGemini APIは呼ばず、生成部分を差し替えて挙動だけを確認する。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db, settings_store as store
from app.main import app
from app.services import gemini

client = TestClient(app)


@pytest.fixture
def with_key(monkeypatch):
    """APIキーが設定済みの状態にする。"""
    monkeypatch.setattr(store, "resolve_gemini_api_key", lambda: "dummy-key")
    monkeypatch.setattr(store, "resolve_gemini_model", lambda: "dummy-model")


def test_generates_and_saves(with_key, monkeypatch):
    """生成結果を返し、DBに記録する。"""
    monkeypatch.setattr(
        gemini, "generate",
        lambda *a, **k: gemini.GenerateResult(text="無事に過ごせただけで満点です。", model="dummy-model"),
    )
    res = client.post("/api/v1/reflection", json={"text": "今日は何もできなかった", "level": 4, "felt": 1})
    assert res.status_code == 200
    body = res.json()
    assert body["reply"] == "無事に過ごせただけで満点です。"
    assert body["fallback"] is False

    conn = db.get_conn()
    try:
        row = conn.execute("SELECT user_text, level, felt FROM reflection").fetchone()
    finally:
        conn.close()
    assert row["user_text"] == "今日は何もできなかった"
    assert row["level"] == 4
    assert row["felt"] == 1


def test_falls_back_when_generation_fails(with_key, monkeypatch):
    """生成に失敗しても200で肯定を返す。

    ここで500を返すと「吐き出したのに無視された」体験になるため、必ず何かを返す。
    """
    def boom(*a, **k):
        raise gemini.GeminiCallFailed("network down")

    monkeypatch.setattr(gemini, "generate", boom)
    res = client.post("/api/v1/reflection", json={"text": "つらい"})
    assert res.status_code == 200
    assert res.json()["fallback"] is True
    assert res.json()["reply"]
    assert res.json()["model"] is None
    # 上限到達（reason='limit'）と同じ見た目にしない。対処が正反対のため
    assert res.json()["reason"] == "error"


def test_limit_and_failure_are_distinguishable(with_key, monkeypatch):
    """上限到達と生成失敗は、どちらも 200 + fallback + model:null で返るが reason で区別できる。

    ここが同じだと「Geminiが壊れた」のか「今日はもう話した」のか判別できない。
    実際にその切り分けに失敗した記録が docs/gemini-fallback-fixes-2026-08-02.txt にある。
    """
    from app.services import usage_limit

    monkeypatch.setattr(
        gemini, "generate",
        lambda *a, **k: gemini.GenerateResult(text="満点です。", model="dummy-model"),
    )
    limit = usage_limit.limit_for("reflection")
    for _ in range(limit):
        assert client.post("/api/v1/reflection", json={"text": "あ"}).json()["reason"] is None

    body = client.post("/api/v1/reflection", json={"text": "あ"}).json()
    assert body["reason"] == "limit"
    assert body["fallback"] is True
    # 上限に達しても受け取って保存する（門前払いしない）
    assert body["reply"]


def test_requires_api_key(monkeypatch):
    """APIキーが無ければ409を返す。"""
    monkeypatch.setattr(store, "resolve_gemini_api_key", lambda: None)
    res = client.post("/api/v1/reflection", json={"text": "つらい"})
    assert res.status_code == 409


def test_rejects_empty_text(with_key):
    """空文字は受け付けない。"""
    res = client.post("/api/v1/reflection", json={"text": ""})
    assert res.status_code == 422
