"""気象取得とストレス指数算出のまとめ役（docs/design.md §3.1 の atmosphere）。

/atmosphere と /daily-plan の両方が同じ観測値を必要とするため、取得・整形・保存を
ここに集約する。ルーター側は表示形式に専念する。

フォールバック方針:
    Open-Meteo に到達できない場合、SQLite に保存した直近のスナップショットから復元する。
    ネットワーク側の事情で通信が落ちるのは日常的に起こるため、そのたびに画面が真っ白に
    なるのは避ける。ただし古すぎる値で「今日の気圧」を語るのは誠実でないので、
    STALE_LIMIT_HOURS を超えたものは使わない。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..db import get_conn
from . import open_meteo
from .budget import DailyContext, discomfort_index
from .open_meteo import JST, AtmosphereUnavailable, HourlySeries
from .pressure import PressureStress, pressure_stress

# 気圧グラフの表示範囲（docs/design.md §8.1）。過去24h〜予報12h
CHART_PAST_HOURS = 24
CHART_FUTURE_HOURS = 12

# 保存済みスナップショットを再利用してよい上限
STALE_LIMIT_HOURS = 6


@dataclass(frozen=True)
class Chart:
    """気圧グラフ用に切り出した時系列。now_index が現在時刻を指す。"""
    times: list[str]
    pressure: list[float]
    now_index: int


@dataclass(frozen=True)
class Observation:
    """その時点の気象観測値と、そこから導いた指標。"""
    latitude: float
    longitude: float
    observed_at: str            # ISO8601（JST）
    pressure: float
    temperature: float
    humidity: float
    stress: PressureStress
    temp_delta_vs_yesterday: float
    discomfort_index: float
    chart: Chart
    source: str
    stale: bool                 # 保存済みスナップショットから復元したか


def _slice_chart(series: HourlySeries) -> Chart:
    """グラフ表示用に過去24h〜予報12hだけを切り出す。"""
    start = max(series.now_index - CHART_PAST_HOURS, 0)
    end = min(series.now_index + CHART_FUTURE_HOURS + 1, len(series.times))
    return Chart(
        times=series.times[start:end],
        pressure=series.pressure[start:end],
        now_index=series.now_index - start,
    )


def _build(series: HourlySeries, *, stale: bool) -> Observation:
    """時系列から観測値と指標を組み立てる。"""
    i = series.now_index
    stress = pressure_stress(series.pressure, i)
    temp_now = series.temperature[i]
    humid_now = series.humidity[i]
    # 「前日比」は前日同時刻との差。日平均ではなく同時刻同士で比べる
    temp_delta = temp_now - series.temperature[i - 24]

    return Observation(
        latitude=series.latitude,
        longitude=series.longitude,
        observed_at=f"{series.times[i]}+09:00",
        pressure=series.pressure[i],
        temperature=temp_now,
        humidity=humid_now,
        stress=stress,
        temp_delta_vs_yesterday=temp_delta,
        discomfort_index=discomfort_index(temp_now, humid_now),
        chart=_slice_chart(series),
        source=series.source,
        stale=stale,
    )


def _save_snapshot(obs: Observation, series: HourlySeries) -> None:
    """スナップショットを保存する。

    raw_json には「ストレス指数を再計算できるだけの時系列」を入れる。
    §4.1 が必要とするのは過去24hと予報6hで、グラフ用の切り出し（過去24h〜予報12h）が
    それを内包するため、この範囲を保存すれば復元時に同じ値を再現できる。
    """
    chart = obs.chart
    start = series.now_index - chart.now_index
    end = start + len(chart.times)
    raw = {
        "times": chart.times,
        "pressure": chart.pressure,
        "temperature": series.temperature[start:end],
        "humidity": series.humidity[start:end],
        "now_index": chart.now_index,
    }
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO atmosphere_snapshot "
            "(observed_at, latitude, longitude, pressure, temperature, humidity, "
            " stress_score, source, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                obs.observed_at, obs.latitude, obs.longitude, obs.pressure,
                obs.temperature, obs.humidity, obs.stress.score, obs.source,
                json.dumps(raw, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _load_snapshot(latitude: float, longitude: float, now: datetime) -> Observation | None:
    """直近のスナップショットから観測値を復元する。無ければ None。"""
    conn = get_conn()
    try:
        # 緯度経度が概ね一致するものだけを使う。0.05度＝約5km。
        # 別の都市の値で「今日の気圧」を語らないための絞り込み
        row = conn.execute(
            "SELECT * FROM atmosphere_snapshot "
            "WHERE ABS(latitude - ?) < 0.05 AND ABS(longitude - ?) < 0.05 "
            "ORDER BY id DESC LIMIT 1",
            (latitude, longitude),
        ).fetchone()
    finally:
        conn.close()

    if row is None or not row["raw_json"]:
        return None

    observed = datetime.fromisoformat(row["observed_at"])
    if now - observed > timedelta(hours=STALE_LIMIT_HOURS):
        return None

    raw = json.loads(row["raw_json"])
    series = HourlySeries(
        latitude=row["latitude"],
        longitude=row["longitude"],
        times=raw["times"],
        pressure=raw["pressure"],
        temperature=raw["temperature"],
        humidity=raw["humidity"],
        now_index=raw["now_index"],
        source=row["source"],
    )
    return _build(series, stale=True)


def current(latitude: float, longitude: float, *, now: datetime | None = None) -> Observation:
    """現在の観測値を返す。取得に失敗した場合は直近のスナップショットで代替する。"""
    now = now or datetime.now(JST)
    try:
        series = open_meteo.fetch(latitude, longitude, now=now)
    except AtmosphereUnavailable:
        fallback = _load_snapshot(latitude, longitude, now)
        if fallback is not None:
            return fallback
        raise

    obs = _build(series, stale=False)
    _save_snapshot(obs, series)
    return obs


def to_context(obs: Observation) -> DailyContext:
    """観測値を体力予算の入力へ変換する。

    フェーズ1では気象因子だけが埋まる。睡眠・拘束・メールは None のままで、
    内訳にも現れない（docs/design.md §4.2 のフェーズ分割）。
    """
    return DailyContext(
        stress=obs.stress,
        temp_delta_vs_yesterday=obs.temp_delta_vs_yesterday,
        discomfort_index=obs.discomfort_index,
        humidity=obs.humidity,
    )
