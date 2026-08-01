"""省エネレベルの決定と提案選定の検証（docs/design.md §4.2 / §4.2.1 / §4.3）。"""
from __future__ import annotations

import pytest

from app.config import suggestions
from app.services.budget import DailyContext, discomfort_index, energy_budget
from app.services.planner import (
    budget_to_level,
    build_plan,
    pick_suggestions,
    resolve_level,
    stress_to_level_floor,
)
from app.services.pressure import pressure_stress

from _scenarios import NOW_INDEX, SCENARIOS


def _context(sc) -> DailyContext:
    """フェーズ1の入力（気象因子のみ）を組み立てる。"""
    return DailyContext(
        stress=pressure_stress(sc.pressure, NOW_INDEX),
        temp_delta_vs_yesterday=sc.temp_delta,
        discomfort_index=discomfort_index(sc.temp, sc.humidity),
        humidity=sc.humidity,
    )


# --- §4.2.1 の解決: ストレス下限マッピング -------------------------------------

@pytest.mark.parametrize("sc", SCENARIOS, ids=lambda s: s.id)
def test_phase1_levels(sc):
    """フェーズ1（気象因子のみ）で期待どおりのレベルになること。"""
    assert build_plan(_context(sc)).level == sc.expected_level_phase1


def test_typhoon_reaches_level5_without_other_factors():
    """台風接近時、気象因子だけでレベル5に到達すること。

    これが §4.2.1 の矛盾の核心。予算だけで決めると、フェーズ1で引ける点は
    気象40＋気温10＋湿度10＝最大60しかなく、予算の下限が40のためレベル3止まりになる。
    「今日は気圧のせいです」を掲げるプロダクトとして、これは成立しない。
    """
    ctx = _context(SCENARIOS[0])
    plan = build_plan(ctx)

    assert plan.level == 5
    # 予算だけで決めていたらレベル3だったことを明示しておく
    assert budget_to_level(plan.energy_budget) == 3
    assert plan.level_driven_by_pressure is True


def test_budget_wins_when_it_is_lower():
    """予算側がより深いレベルを示す場合は、そちらが採用される（下限であって固定ではない）。

    フェーズ2以降で睡眠不足や拘束時間が加わったときの動作。
    """
    sc = SCENARIOS[1]  # 梅雨の曇天。ストレス39.1 → 下限はレベル2
    ctx = _context(sc)
    assert build_plan(ctx).level == 2

    # 睡眠2時間・拘束6時間・メール15件を加えると予算が落ちる
    ctx.sleep_hours = 2.0
    ctx.busy_hours = 6.0
    ctx.actionable_mail_count = 15
    plan = build_plan(ctx)

    assert plan.level >= 3
    assert plan.level_driven_by_pressure is False


@pytest.mark.parametrize("stress,expected", [
    (95.0, 5), (90.0, 5), (89.9, 4), (75.0, 4), (74.9, 3),
    (55.0, 3), (54.9, 2), (35.0, 2), (34.9, 1), (0.0, 1),
])
def test_stress_floor_boundaries(stress, expected):
    """ストレス下限マッピングの境界値。"""
    assert stress_to_level_floor(stress) == expected


@pytest.mark.parametrize("budget,expected", [
    (100, 1), (80, 1), (79, 2), (60, 2), (59, 3), (40, 3), (39, 4), (20, 4), (19, 5), (0, 5),
])
def test_budget_boundaries(budget, expected):
    """体力予算からレベルへの写像の境界値（§4.3）。"""
    assert budget_to_level(budget) == expected


def test_resolve_level_takes_the_deeper_one():
    """最終レベルは「予算由来」と「ストレス由来の下限」の大きい方。"""
    assert resolve_level(budget=90, stress_score=95.0) == (5, True)   # ストレス側が深い
    assert resolve_level(budget=10, stress_score=0.0) == (5, False)   # 予算側が深い
    assert resolve_level(budget=90, stress_score=0.0) == (1, False)


# --- §4.2 体力予算 -------------------------------------------------------------

def test_unmeasured_factors_do_not_appear():
    """未計測の因子は内訳に現れないこと。

    0（計測して負荷が無かった）と None（まだ計測していない）を区別する。
    フェーズ1で「睡眠不足 0点」と表示すると、記録を促す圧力になる（§1.3）。
    """
    names = [f.name for f in build_plan(_context(SCENARIOS[0])).breakdown]
    assert "睡眠不足" not in names
    assert "予定の拘束" not in names
    assert "要対応メール・ToDo" not in names


def test_each_factor_is_capped():
    """単一因子が予算を食い尽くさないこと（§4.2 の設計判断）。"""
    ctx = _context(SCENARIOS[2])
    ctx.sleep_hours = 0.0          # 係数どおりなら35点だが上限20
    ctx.busy_hours = 24.0          # 同48点だが上限15
    ctx.actionable_mail_count = 999
    result = energy_budget(ctx)

    for f in result.factors:
        assert f.cost <= f.cap + 1e-9, f"{f.name} が上限を超えている"
    assert result.budget >= 0


def test_breakdown_is_sorted_by_impact():
    """内訳は影響の大きい順に並ぶこと。上から数件しか読まれないため。"""
    costs = [f.cost for f in build_plan(_context(SCENARIOS[2])).breakdown]
    assert costs == sorted(costs, reverse=True)


# --- §4.3 提案の選定 -----------------------------------------------------------

@pytest.mark.parametrize("level", [1, 2, 3, 4, 5])
def test_suggestions_never_exceed_the_level(level):
    """そのレベルで許される負荷を超える提案を出さないこと（上振れ禁止）。"""
    by_id = {s["id"]: s for s in suggestions()}
    for s in pick_suggestions(level):
        assert by_id[s.id]["load"] >= level


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_at_most_three_suggestions(level):
    """1日に提示するのは最大3件。多いこと自体が負荷になるため。"""
    assert 1 <= len(pick_suggestions(level)) <= 3


def test_level5_shows_only_one():
    """レベル5では1件のみ、かつ『何もしない』であること。"""
    picked = pick_suggestions(5)
    assert len(picked) == 1
    assert picked[0].id == "nothing"


def test_heaviest_allowed_comes_first():
    """そのレベルで許される上限に近いものから選ぶこと。

    軽い順に選ぶと全レベルで「何もしない」が筆頭になり、レベルの差が消える
    （モックアップ実装時に判明した不具合）。
    """
    by_id = {s["id"]: s for s in suggestions()}
    picked = pick_suggestions(1)
    loads = [by_id[s.id]["load"] for s in picked]
    assert loads == sorted(loads)      # load昇順 = 重い順
    assert picked[0].id == "outing"    # レベル1の筆頭は最も重い提案


def test_no_suggestion_pool_entry_increases_load_beyond_level5():
    """提案プールに load が範囲外の項目が混ざっていないこと。"""
    for s in suggestions():
        assert 1 <= int(s["load"]) <= 5, s["id"]
