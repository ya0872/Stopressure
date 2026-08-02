"""利用回数の遮断が機能していることを検証する（F-16 / docs/design.md §4.8）。

フロント側のブロックは React の state だけで持っており、リロードで消え、curl で
:8000 を直接叩けば迂回できる。強制力があるのはバックエンドだけなので、その担保を
ここで検証する。

このファイルの中心は test_gemini_is_not_called_when_blocked。
「429を返す」ことではなく「LLMを呼ばない」ことが要件であり、順序を間違えて
Geminiを呼んでから429を返す実装になっても、ステータスコードだけ見るテストでは通ってしまう。
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import db, settings_store as store
from app.main import app
from app.services import gemini, usage_limit

client = TestClient(app)

# フェーズ1（6時〜12時）の途中。ここを基準に時刻を動かす
BASE_NOW = datetime(2026, 8, 2, 10, 0)


@pytest.fixture
def with_key(monkeypatch):
    """APIキーが設定済みの状態にする。"""
    monkeypatch.setattr(store, "resolve_gemini_api_key", lambda: "dummy-key")
    monkeypatch.setattr(store, "resolve_gemini_model", lambda: "dummy-model")


@pytest.fixture
def spy_gemini(monkeypatch):
    """Geminiの呼び出しを記録する。実際のAPIは叩かない。"""
    calls: list[tuple] = []

    def fake(*args, **kwargs):
        calls.append(args)
        return gemini.GenerateResult(text="ダミー応答", model="dummy-model")

    monkeypatch.setattr(gemini, "generate", fake)
    return calls


@pytest.fixture
def small_limit(monkeypatch):
    """上限を2回に縮める。設定値そのものではなく遮断の挙動を見るため。"""
    monkeypatch.setattr(usage_limit, "limit_for", lambda endpoint: 2)


@pytest.fixture
def frozen_now(monkeypatch):
    """時刻を固定する。holder["now"] を書き換えれば時間を進められる。"""
    holder = {"now": BASE_NOW}
    monkeypatch.setattr(usage_limit, "_now", lambda: holder["now"])
    return holder


def _post_generate():
    return client.post("/api/v1/generate", json={"purpose": "meal", "level": 3})

def test_allows_up_to_limit(with_key, spy_gemini, small_limit, frozen_now):
    """上限までは通る。"""
    assert _post_generate().status_code == 200
    assert _post_generate().status_code == 200
    assert len(spy_gemini) == 2


def test_blocks_over_limit(with_key, spy_gemini, small_limit, frozen_now):
    """上限を超えたら429を返す。"""
    _post_generate()
    _post_generate()
    res = _post_generate()
    assert res.status_code == 429


def test_gemini_is_not_called_when_blocked(with_key, spy_gemini, small_limit, frozen_now):
    """遮断されたリクエストでLLMを呼ばない。

    このテストがこのファイルの核心。「429を返す」ではなく「LLMの処理を行わない」が
    要件なので、呼び出し回数そのものを見る。
    """
    _post_generate()
    _post_generate()
    assert len(spy_gemini) == 2

    for _ in range(5):
        assert _post_generate().status_code == 429

    # 5回はじかれても、Geminiへの呼び出しは増えていない
    assert len(spy_gemini) == 2


def test_block_message_avoids_the_word_restriction(with_key, spy_gemini, small_limit, frozen_now):
    _post_generate()
    _post_generate()
    detail = _post_generate().json()["detail"]
    assert "制限" not in detail
    assert "またお聞きします" in detail


def test_failed_generation_does_not_consume_quota(with_key, small_limit, frozen_now, monkeypatch):
    """Gemini側の障害で利用枠を失わない。

    先に加算する実装だと、通信断が続いただけで「今日はもう話せない」状態になる。
    """
    def boom(*a, **k):
        raise gemini.GeminiCallFailed("network down")

    monkeypatch.setattr(gemini, "generate", boom)
    for _ in range(5):
        assert _post_generate().status_code == 502

    # 502が5回続いた後でも、回復すれば上限ぶんは使える
    monkeypatch.setattr(
        gemini, "generate",
        lambda *a, **k: gemini.GenerateResult(text="ok", model="dummy-model"),
    )
    assert _post_generate().status_code == 200
    assert _post_generate().status_code == 200
    assert _post_generate().status_code == 429


# --- フェーズと日付によるリセット ---------------------------------------------


def test_counter_resets_on_next_phase(with_key, spy_gemini, small_limit, frozen_now):
    """フェーズが変わるとまた使える。"""
    _post_generate()
    _post_generate()
    assert _post_generate().status_code == 429

    # 10:00（フェーズ1）→ 13:00（フェーズ2）
    frozen_now["now"] = BASE_NOW.replace(hour=13)
    assert _post_generate().status_code == 200


def test_counter_resets_on_next_day(with_key, spy_gemini, small_limit, frozen_now):
    """日付が変わるとまた使える。フェーズ番号が同じでも別枠になる。"""
    _post_generate()
    _post_generate()
    assert _post_generate().status_code == 429

    # 8/2 10:00 → 8/3 10:00。どちらもフェーズ1だが、日付が違うので別の行になる
    frozen_now["now"] = BASE_NOW.replace(day=3)
    assert _post_generate().status_code == 200


def test_phase_boundaries():
    """フェーズの区切りが 0/6/12/18時 であること。フロントの currentPhase() と同じ定義。"""
    assert usage_limit.current_phase(datetime(2026, 8, 2, 0, 0)) == 0
    assert usage_limit.current_phase(datetime(2026, 8, 2, 5, 59)) == 0
    assert usage_limit.current_phase(datetime(2026, 8, 2, 6, 0)) == 1
    assert usage_limit.current_phase(datetime(2026, 8, 2, 23, 59)) == 3


def test_last_phase_resets_at_midnight():
    """フェーズ3の次は翌日の0時。日付をまたぐ計算を間違えていないこと。"""
    assert usage_limit.next_phase_at(datetime(2026, 8, 2, 20, 30)) == datetime(2026, 8, 3, 0, 0)
    assert usage_limit.next_phase_at(datetime(2026, 8, 2, 10, 0)) == datetime(2026, 8, 2, 12, 0)


# --- 夜の吐き出しの扱い -------------------------------------------------------


def test_reflection_is_never_rejected(with_key, spy_gemini, small_limit, frozen_now):
    """上限に達しても429で突き返さない。

    /generate と違い、ここは自由文を受け止める場所である。門前払いすると
    routers/reflection.py が避けようとしている「吐き出したのに無視された」体験になる。
    """
    for _ in range(2):
        assert client.post("/api/v1/reflection", json={"text": "つらい"}).status_code == 200
    assert len(spy_gemini) == 2

    res = client.post("/api/v1/reflection", json={"text": "まだつらい"})
    assert res.status_code == 200
    assert res.json()["fallback"] is True
    assert res.json()["model"] is None
    # 上限後はLLMを呼んでいない（定型文で応じている）
    assert len(spy_gemini) == 2


def test_reflection_still_records_text_when_blocked(with_key, spy_gemini, small_limit, frozen_now):
    """上限後に書いた内容もDBに残す。受け取っていないことにはしない。"""
    for _ in range(3):
        client.post("/api/v1/reflection", json={"text": "つらい"})
    client.post("/api/v1/reflection", json={"text": "上限後の言葉"})

    conn = db.get_conn()
    try:
        rows = conn.execute("SELECT user_text FROM reflection ORDER BY id").fetchall()
    finally:
        conn.close()
    assert "上限後の言葉" in [r["user_text"] for r in rows]

def test_usage_does_not_leak_counts(with_key, spy_gemini, small_limit, frozen_now):
    """回数を返さない（§1.2 のカウント表示の禁止）。"""
    _post_generate()
    body = client.get("/api/v1/usage").json()

    assert set(body.keys()) == {"blocked", "resets_at", "message", "endpoints"}
    assert body["endpoints"]["generate"] == {"blocked": False}
    # レスポンス全体を文字列にしても、残り回数を推測できる数字が出ていないこと
    assert "count" not in str(body)
    assert "remaining" not in str(body)


def test_usage_reports_partial_block(with_key, spy_gemini, small_limit, frozen_now):
    """一部が尽きただけでは全体をブロック扱いにしない（§4.8）。"""
    _post_generate()
    _post_generate()

    body = client.get("/api/v1/usage").json()
    assert body["endpoints"]["generate"]["blocked"] is True
    assert body["endpoints"]["reflection"]["blocked"] is False
    assert body["blocked"] is False
    assert body["message"] is None

def test_only_interactive_endpoints_are_limited():
    """制限対象は対話機能だけ。省エネ度の閲覧は常時できなければならない（§4.8）。

    ここに 'plan' や 'atmosphere' を足すと、体調を確認する手段そのものを塞ぐことになる。
    """
    assert set(usage_limit.ENDPOINTS) == {"generate", "reflection"}


def test_limits_are_configured():
    """thresholds.yaml に上限が書かれていること。

    設定漏れを既定値で握り潰すと、防御が黙って無効化される。
    """
    for endpoint in usage_limit.ENDPOINTS:
        assert usage_limit.limit_for(endpoint) > 0


def test_health_is_not_limited(with_key, spy_gemini, small_limit, frozen_now):
    """閲覧系は回数を消費しない。"""
    for _ in range(10):
        assert client.get("/api/v1/health").status_code == 200
    assert _post_generate().status_code == 200
