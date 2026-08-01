"""気圧ストレス指数の検証（docs/design.md §4.1）。"""
from __future__ import annotations

import pytest

from app.services.pressure import pressure_stress

from _scenarios import NOW_INDEX, SCENARIOS


@pytest.mark.parametrize("sc", SCENARIOS, ids=lambda s: s.id)
def test_matches_mockup(sc):
    """モックアップ（mockup/index.html）と同じスコアになること。

    アルゴリズムはモックアップとバックエンドの2箇所に実装されている。
    片方だけ直すと画面と実データで違う値が出るため、ここで一致を固定する。
    """
    st = pressure_stress(sc.pressure, NOW_INDEX)
    assert st.score == pytest.approx(sc.expected_stress, abs=0.05)


def test_rising_pressure_scores_zero():
    """気圧が上がり続ける日は加点しない。

    絶対値ではなく「下がる過程」を評価するという設計判断（§4.1）の確認。
    """
    rising = [1000.0 + i * 0.5 for i in range(36)]
    assert pressure_stress(rising, NOW_INDEX).score == 0.0


def test_high_altitude_flat_pressure_is_not_penalized():
    """気圧が低いまま安定している場合、絶対値の補助点(最大10)しか付かない。

    標高の高い地域を常時「低気圧」と誤判定しないための確認。
    """
    flat_low = [960.0] * 36
    st = pressure_stress(flat_low, NOW_INDEX)
    assert st.score == 10.0
    assert st.delta_6h == 0.0


def test_each_term_is_capped():
    """単一の項が上限を超えないこと。上限が無いと1因子で満点になる。"""
    # 6時間で20hPa低下（係数10なら200点だが、上限40で頭打ちになる）
    crash = [1010.0] * 19 + [1010.0 - i * 4 for i in range(1, 18)]
    st = pressure_stress(crash, NOW_INDEX)
    assert st.score <= 100.0
    assert st.delta_6h < -20


def test_forecast_is_included():
    """予報の低下が先行評価されること（体調は気圧に先行して崩れるため）。"""
    # 現在まで平坦で、これから下がるだけの系列
    flat_then_drop = [1010.0] * 25 + [1010.0 - i for i in range(1, 12)]
    st = pressure_stress(flat_then_drop, NOW_INDEX)
    assert st.delta_6h == 0.0
    assert st.delta_next6h < 0
    assert st.score > 0


def test_short_series_is_rejected():
    """過去24h・予報6hが揃っていない系列は受け付けない。"""
    with pytest.raises(ValueError):
        pressure_stress([1000.0] * 26, NOW_INDEX)
