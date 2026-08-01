"""Open-Meteo から気圧・気温・湿度の時系列を取得する（docs/design.md §7.1）。

フェーズ1の主系統。実測と予報を1つのAPIで賄えるため実装が最短になる。
中核アルゴリズム（§4.1）が予報気圧を使う以上、予報を返せないAPIでは成立しない。
フェーズ2で気象庁アメダス（10分粒度の実測）を併用する。

APIキー不要・非商用無料。出典表示の義務は無いが、気象庁を併用する段階では必要になる。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

ENDPOINT = "https://api.open-meteo.com/v1/forecast"

# 日本標準時。DSTが無いため固定オフセットで正確に表せる（tzdataへの依存を避ける）
JST = timezone(timedelta(hours=9))

# 過去2日・予報2日を取る。§4.1 が過去24hと予報6hを要求するため、
# 現在時刻が今日の何時であっても両端が足りるだけの余裕を持たせている
PAST_DAYS = 2
FORECAST_DAYS = 2

# 取得結果のキャッシュ有効期間（秒）。Open-Meteoの更新は1時間ごとなので10分で十分
CACHE_TTL_SEC = 600

_cache: dict[tuple[float, float], tuple[float, "HourlySeries"]] = {}


class AtmosphereUnavailable(RuntimeError):
    """気象データを取得できなかった。"""


@dataclass(frozen=True)
class HourlySeries:
    """1時間ごとの気象時系列。now_index が現在時刻に対応する。"""
    latitude: float
    longitude: float
    times: list[str]          # "2026-08-01T14:00" 形式のJSTローカル時刻
    pressure: list[float]     # 海面更正気圧(hPa)
    temperature: list[float]  # 気温(℃)
    humidity: list[float]     # 相対湿度(%)
    now_index: int
    source: str = "open-meteo"


def _now_index(times: list[str], now: datetime) -> int:
    """現在時刻に対応するインデックスを返す。

    ISO形式の文字列は辞書順と時刻順が一致するため、文字列比較で「現在以下で最も新しい」
    ものを選べる。APIが返す時刻が丸め方の違いで一致しない場合への保険。
    """
    key = now.strftime("%Y-%m-%dT%H:00")
    try:
        return times.index(key)
    except ValueError:
        pass

    candidates = [i for i, t in enumerate(times) if t <= key]
    if not candidates:
        raise AtmosphereUnavailable(f"現在時刻({key})に対応する観測値がありません")
    return candidates[-1]


def fetch(latitude: float, longitude: float, *, now: datetime | None = None) -> HourlySeries:
    """気象時系列を取得する。TTL内は同じ結果を返す。"""
    now = now or datetime.now(JST)
    key = (round(latitude, 3), round(longitude, 3))

    cached = _cache.get(key)
    if cached and (time.monotonic() - cached[0]) < CACHE_TTL_SEC:
        return cached[1]

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "pressure_msl,temperature_2m,relative_humidity_2m",
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "timezone": "Asia/Tokyo",
    }
    try:
        res = httpx.get(ENDPOINT, params=params, timeout=20.0)
        res.raise_for_status()
        payload = res.json()
    except httpx.HTTPError as e:
        # 原因が環境側にあることが多い。
        # 呼び出し側でフォールバックを判断できるよう専用の例外に包む
        raise AtmosphereUnavailable(f"Open-Meteoに接続できませんでした: {e}") from e

    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    pressure = hourly.get("pressure_msl") or []
    temperature = hourly.get("temperature_2m") or []
    humidity = hourly.get("relative_humidity_2m") or []

    if not times or len(pressure) != len(times):
        raise AtmosphereUnavailable("Open-Meteoの応答に気圧の時系列が含まれていません")
    # 予報値に欠測(null)が混じることがある。前後で補間せず、欠測があれば取得失敗として扱う
    if any(v is None for v in pressure):
        raise AtmosphereUnavailable("気圧の時系列に欠測があります")

    series = HourlySeries(
        latitude=payload.get("latitude", latitude),
        longitude=payload.get("longitude", longitude),
        times=times,
        pressure=[float(v) for v in pressure],
        temperature=[float(v) if v is not None else float("nan") for v in temperature],
        humidity=[float(v) if v is not None else float("nan") for v in humidity],
        now_index=_now_index(times, now),
    )
    _cache[key] = (time.monotonic(), series)
    return series


def clear_cache() -> None:
    """キャッシュを捨てる。テストと手動リフレッシュ用。"""
    _cache.clear()
