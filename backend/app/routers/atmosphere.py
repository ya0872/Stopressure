"""気象生データと気圧ストレス指数を返す（docs/design.md §5 / F-01）。

位置情報はブラウザの Geolocation API から渡す想定（§11 #7）。拒否された場合に備えて
既定値を持たせてあり、パラメータ無しでも動く。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services import atmosphere
from ..services.open_meteo import AtmosphereUnavailable

router = APIRouter(prefix="/atmosphere", tags=["atmosphere"])

# 既定の地点。石川県野々市市（§7.1 の注記どおり、気象庁を使う段階では金沢56227で代替する）
DEFAULT_LAT = 36.5297
DEFAULT_LON = 136.6094


class StressDetail(BaseModel):
    score: float = Field(description="気圧ストレス指数（0〜100、大きいほど身体負荷が高い）")
    delta_6h: float = Field(description="直近6時間の気圧変化(hPa)。負が低下")
    delta_24h: float = Field(description="直近24時間の気圧変化(hPa)")
    delta_next6h: float = Field(description="これから6時間の予報変化(hPa)")


class ChartSeries(BaseModel):
    times: list[str] = Field(description="JSTのローカル時刻")
    pressure: list[float]
    now_index: int = Field(description="times のうち現在時刻に対応する位置")


class AtmosphereResponse(BaseModel):
    latitude: float
    longitude: float
    observed_at: str
    source: str = Field(description="open-meteo | jma")
    stale: bool = Field(description="通信に失敗し、保存済みの値で代替したか")
    pressure: float = Field(description="海面更正気圧(hPa)")
    temperature: float
    humidity: float
    temp_delta_vs_yesterday: float = Field(description="前日同時刻比(℃)")
    discomfort_index: float
    stress: StressDetail
    chart: ChartSeries = Field(description="気圧グラフ用。過去24h〜予報12h")


@router.get("", response_model=AtmosphereResponse)
def get_atmosphere(
    lat: float = Query(default=DEFAULT_LAT, ge=-90, le=90),
    lon: float = Query(default=DEFAULT_LON, ge=-180, le=180),
) -> AtmosphereResponse:
    """現在地の気象データと気圧ストレス指数を返す。"""
    try:
        obs = atmosphere.current(lat, lon)
    except AtmosphereUnavailable as e:
        # 保存済みの値も無い場合だけここに来る。プロキシ設定が原因のことが多いため
        # メッセージをそのまま見せて、環境側の切り分けができるようにする
        raise HTTPException(status_code=503, detail=str(e)) from e

    return AtmosphereResponse(
        latitude=obs.latitude,
        longitude=obs.longitude,
        observed_at=obs.observed_at,
        source=obs.source,
        stale=obs.stale,
        pressure=obs.pressure,
        temperature=obs.temperature,
        humidity=obs.humidity,
        temp_delta_vs_yesterday=round(obs.temp_delta_vs_yesterday, 1),
        discomfort_index=round(obs.discomfort_index, 1),
        stress=StressDetail(
            score=round(obs.stress.score, 1),
            delta_6h=round(obs.stress.delta_6h, 1),
            delta_24h=round(obs.stress.delta_24h, 1),
            delta_next6h=round(obs.stress.delta_next6h, 1),
        ),
        chart=ChartSeries(
            times=obs.chart.times, pressure=obs.chart.pressure, now_index=obs.chart.now_index
        ),
    )
