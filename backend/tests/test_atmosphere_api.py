"""/atmosphere と /daily-plan の検証。

外部APIには接続せず、open_meteo.fetch を差し替えて動かす。テストがネットワーク環境や
Open-Meteoの稼働状況に左右されないようにするため。
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import atmosphere, open_meteo
from app.services.open_meteo import JST, AtmosphereUnavailable

from _scenarios import SCENARIOS, hourly_series as _series

client = TestClient(app)


@pytest.fixture
def typhoon(monkeypatch):
    """台風接近シナリオを返すように気象APIを差し替える。"""
    monkeypatch.setattr(open_meteo, "fetch", lambda lat, lon, now=None: _series(SCENARIOS[0]))
    open_meteo.clear_cache()
    return SCENARIOS[0]


def test_atmosphere_returns_stress_and_chart(typhoon):
    res = client.get("/api/v1/atmosphere")
    assert res.status_code == 200
    body = res.json()

    assert body["stress"]["score"] == pytest.approx(typhoon.expected_stress, abs=0.05)
    assert body["stress"]["delta_6h"] < 0
    assert body["stale"] is False
    assert body["source"] == "open-meteo"
    assert body["temp_delta_vs_yesterday"] == pytest.approx(typhoon.temp_delta, abs=0.05)

    # グラフは過去24h〜予報12h（docs/design.md §8.1）
    chart = body["chart"]
    assert chart["now_index"] == 24
    assert len(chart["times"]) == len(chart["pressure"])
    assert len(chart["times"]) <= 24 + 12 + 1


def test_daily_plan_shape(typhoon):
    res = client.get("/api/v1/daily-plan")
    assert res.status_code == 200
    body = res.json()

    assert body["level"] == 5
    assert body["level_name"] == "完全休止"
    assert body["level_driven_by_pressure"] is True
    assert len(body["suggestions"]) == 1
    assert body["suggestions"][0]["id"] == "nothing"
    assert body["breakdown"], "内訳が空になっている"
    assert body["breakdown"][0]["factor"] == "気圧の低下"


def test_location_is_configurable(monkeypatch):
    """緯度経度を渡せること（ブラウザの Geolocation から受け取る想定）。"""
    seen: dict[str, float] = {}

    def fake(lat, lon, now=None):
        seen["lat"], seen["lon"] = lat, lon
        return _series(SCENARIOS[4])

    monkeypatch.setattr(open_meteo, "fetch", fake)
    res = client.get("/api/v1/daily-plan", params={"lat": 35.0, "lon": 135.0})

    assert res.status_code == 200
    assert seen == {"lat": 35.0, "lon": 135.0}


def test_invalid_location_is_rejected():
    assert client.get("/api/v1/atmosphere", params={"lat": 200, "lon": 0}).status_code == 422


# --- 通信断のフォールバック ----------------------------------------------------

def test_falls_back_to_snapshot(monkeypatch):
    """通信に失敗しても、直近のスナップショットで画面を保つこと。

    ネットワーク側の事情で通信が落ちるのは日常的に起こる。
    そのたびに画面が真っ白になるのは避ける（§10 リスクと退避策）。
    """
    monkeypatch.setattr(open_meteo, "fetch", lambda lat, lon, now=None: _series(SCENARIOS[0]))
    ok = client.get("/api/v1/daily-plan")
    assert ok.status_code == 200 and ok.json()["stale"] is False

    def boom(lat, lon, now=None):
        raise AtmosphereUnavailable("Open-Meteoに接続できませんでした")

    monkeypatch.setattr(open_meteo, "fetch", boom)
    res = client.get("/api/v1/daily-plan")

    assert res.status_code == 200
    assert res.json()["stale"] is True
    # 復元した時系列から再計算しても同じレベルになること
    assert res.json()["level"] == ok.json()["level"]
    assert res.json()["pressure_stress"] == ok.json()["pressure_stress"]


def test_returns_503_when_nothing_is_available(monkeypatch):
    """スナップショットも無い場合は503を返し、原因をそのまま見せる。"""
    def boom(lat, lon, now=None):
        raise AtmosphereUnavailable("Open-Meteoに接続できませんでした: timeout")

    monkeypatch.setattr(open_meteo, "fetch", boom)
    res = client.get("/api/v1/atmosphere")

    assert res.status_code == 503
    assert "Open-Meteo" in res.json()["detail"]


def test_stale_snapshot_is_not_reused(monkeypatch):
    """古すぎるスナップショットで「今日の気圧」を語らないこと。"""
    old = datetime.now(JST) - timedelta(hours=atmosphere.STALE_LIMIT_HOURS + 2)
    monkeypatch.setattr(open_meteo, "fetch", lambda lat, lon, now=None: _series(SCENARIOS[0], now=old))
    assert client.get("/api/v1/daily-plan").status_code == 200

    def boom(lat, lon, now=None):
        raise AtmosphereUnavailable("接続できません")

    monkeypatch.setattr(open_meteo, "fetch", boom)
    assert client.get("/api/v1/daily-plan").status_code == 503


def test_snapshot_is_not_shared_across_locations(monkeypatch):
    """別の地点のスナップショットをフォールバックに使わないこと。"""
    monkeypatch.setattr(open_meteo, "fetch", lambda lat, lon, now=None: _series(SCENARIOS[0]))
    assert client.get("/api/v1/daily-plan").status_code == 200  # 野々市で保存

    def boom(lat, lon, now=None):
        raise AtmosphereUnavailable("接続できません")

    monkeypatch.setattr(open_meteo, "fetch", boom)
    # 東京で問い合わせても、野々市の値は使わない
    assert client.get("/api/v1/daily-plan", params={"lat": 35.68, "lon": 139.76}).status_code == 503


# --- 禁止事項の回帰テスト（docs/design.md §1.3）--------------------------------

def test_response_has_no_prohibited_fields(typhoon):
    """レスポンスに禁止されたUI要素の材料を含めないこと。

    レスポンスの形がそのままUIの誘導になる。チェックボックスやストリークの
    フィールドがあると、いずれ画面に出てしまう（CLAUDE.md の警告）。
    """
    body = client.get("/api/v1/daily-plan").json()

    for forbidden in ("streak", "carryover", "carried_over", "rank", "comparison", "goal_achieved"):
        assert forbidden not in body, f"禁止フィールド {forbidden} が含まれている"

    for s in body["suggestions"]:
        for forbidden in ("done", "completed", "checked", "checkbox", "is_done"):
            assert forbidden not in s, f"提案に完了状態のフィールド {forbidden} がある"


def test_estimated_capacity_is_not_exposed_yet(typhoon):
    """稼働率（F-17 / §4.6）は未決事項のため、まだ返さないこと。"""
    assert "estimated_capacity" not in client.get("/api/v1/daily-plan").json()
