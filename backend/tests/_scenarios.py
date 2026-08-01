"""テスト用の気象シナリオ。

台風・梅雨・爆弾低気圧・寒冷前線・秋晴れの5パターンで、気圧ストレスと省エネレベルの
算出を固定する。元はモックアップ（mockup/index.html）が持っていた同じ値の写しだったが、
2026-08-01 に画面がライブデータ化して算出ロジックを持たなくなったため、
現在はこちらが唯一の定義になっている。
乱数を使わず sin で揺らぎを与えているため、何度実行しても同じ系列になる。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.services.open_meteo import JST, HourlySeries


def make_series(start: float, end: float, curve: str, n: int = 36) -> list[float]:
    """気圧の時系列を生成する。start から end へ curve の形で変化させる。"""
    arr: list[float] = []
    for i in range(n):
        t = i / (n - 1)
        if curve == "late":       # 後半で急降下
            e = t ** 2.4
        elif curve == "early":    # 前半で下がりきる
            e = 1 - (1 - t) ** 2.4
        else:                     # 直線的
            e = t
        arr.append(round(start + (end - start) * e + math.sin(i * 1.7) * 0.3, 1))
    return arr


@dataclass(frozen=True)
class Scenario:
    id: str
    label: str
    pressure: list[float]
    temp: float
    humidity: float
    temp_delta: float
    # モックアップで検証済みの期待値
    expected_stress: float
    expected_level_phase1: int   # 気象因子のみ（フェーズ1）でのレベル


# 気圧配列は36要素（過去24時間 + 現在 + 予報11時間）。index 24 が現在時刻
NOW_INDEX = 24

SCENARIOS = [
    Scenario("typhoon", "台風接近", make_series(1008, 981, "late"),
             26.0, 88, -2.5, expected_stress=92.9, expected_level_phase1=5),
    Scenario("rainy", "梅雨の曇天", make_series(1010, 1001, "linear"),
             24.0, 84, -1.0, expected_stress=39.1, expected_level_phase1=2),
    Scenario("bomb", "爆弾低気圧", make_series(1012, 976, "late"),
             27.0, 92, -6.0, expected_stress=92.5, expected_level_phase1=5),
    Scenario("front", "寒冷前線通過後", make_series(1004, 1016, "early"),
             15.0, 55, -7.5, expected_stress=0.0, expected_level_phase1=1),
    Scenario("clear", "秋晴れ", make_series(1019, 1021, "linear"),
             21.0, 48, 0.0, expected_stress=0.0, expected_level_phase1=1),
]

# 既定の地点（野々市市）。routers/atmosphere.py の DEFAULT_LAT / DEFAULT_LON と揃える
DEFAULT_LAT = 36.5297
DEFAULT_LON = 136.6094


def hourly_series(sc: Scenario, *, now: datetime | None = None) -> HourlySeries:
    """シナリオから、現在時刻に合わせた HourlySeries を作る。

    open_meteo.fetch の差し替え先として使う。テストがネットワークの状態に
    左右されないようにするため。
    """
    now = (now or datetime.now(JST)).replace(minute=0, second=0, microsecond=0)
    base = now - timedelta(hours=NOW_INDEX)
    n = len(sc.pressure)
    return HourlySeries(
        latitude=DEFAULT_LAT,
        longitude=DEFAULT_LON,
        times=[(base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(n)],
        pressure=sc.pressure,
        # 「前日比」を再現するため、24時間前が現在 - temp_delta になるようにする
        temperature=[sc.temp - sc.temp_delta] * NOW_INDEX + [sc.temp] * (n - NOW_INDEX),
        humidity=[sc.humidity] * n,
        now_index=NOW_INDEX,
    )
