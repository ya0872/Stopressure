"""気圧ストレス指数（docs/design.md §4.1）。

設計判断: 気圧の絶対値ではなく変化率を主軸にする。
体調不良と関連が指摘されるのは「低い気圧」そのものではなく「気圧が急に下がる過程」であるため。
絶対値で判定すると、標高の高い地域では常時「低気圧」となり、台風一過の晴天日にも誤判定する。

この計算は mockup/index.html の pressureStress() と同じ結果になること。
片方だけを変更しないこと（CLAUDE.md の指示）。
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import thresholds


@dataclass(frozen=True)
class PressureStress:
    """気圧ストレス指数と、その根拠になった変化量。

    delta_* は「現在 - 過去」なので、負の値ほど気圧が下がっている。
    画面で「6時間で5.2hPa低下」と説明するために、スコアだけでなく内訳も返す。
    """
    score: float          # 0〜100。大きいほど身体負荷が高い
    delta_6h: float       # 直近6時間の変化量(hPa)
    delta_24h: float      # 直近24時間の変化量(hPa)
    delta_next6h: float   # これから6時間の予報変化量(hPa)
    pressure_now: float   # 現在の海面更正気圧(hPa)


def pressure_stress(hourly_pressure: list[float], now_index: int) -> PressureStress:
    """気圧ストレス指数を算出する。

    hourly_pressure: 1時間ごとの海面更正気圧(hPa)。過去24h以上と予報6h以上を含むこと
    now_index: 現在時刻に対応するインデックス
    """
    if now_index < 24 or now_index + 6 >= len(hourly_pressure):
        raise ValueError(
            f"時系列が足りません（過去24h・予報6hが必要）: now_index={now_index}, len={len(hourly_pressure)}"
        )

    th = thresholds()["pressure_stress"]
    p_now = hourly_pressure[now_index]

    # 短期変化: 直近6時間の低下幅（負の値ほど急降下）
    delta_6h = p_now - hourly_pressure[now_index - 6]
    # 長期変化: 直近24時間の低下幅
    delta_24h = p_now - hourly_pressure[now_index - 24]
    # 先行変化: これから6時間の予報低下幅（体調は先行して崩れるため加味する）
    delta_next6h = hourly_pressure[now_index + 6] - p_now

    score = 0.0
    # 上昇時は加点しない。「下がる過程」だけを評価するため
    if delta_6h < 0:
        score += min(abs(delta_6h) * th["delta_6h"]["coef"], th["delta_6h"]["cap"])
    if delta_24h < 0:
        score += min(abs(delta_24h) * th["delta_24h"]["coef"], th["delta_24h"]["cap"])
    if delta_next6h < 0:
        score += min(abs(delta_next6h) * th["delta_next6h"]["coef"], th["delta_next6h"]["cap"])

    # 絶対値は補助指標に留める
    if p_now < th["absolute"]["base"]:
        score += min(th["absolute"]["base"] - p_now, th["absolute"]["cap"])

    return PressureStress(
        score=min(score, 100.0),
        delta_6h=delta_6h,
        delta_24h=delta_24h,
        delta_next6h=delta_next6h,
        pressure_now=p_now,
    )
