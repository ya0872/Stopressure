"""省エネレベルの決定と提案の選定（docs/design.md §4.2.1 / §4.3）。

レベルの決め方（2026-08-01 決定 / §4.2.1 の解決）:
    level = max(体力予算から求めたレベル, 気圧ストレスから求めた下限レベル)

体力予算だけでレベルを決めると、フェーズ1（気象因子のみ）では引ける点が最大60のため
予算の下限が40になり、レベル4・5に原理的に到達できない。台風でも爆弾低気圧でも
「省エネ（Lv3）」止まりとなり、「今日は気圧のせいです」を掲げるプロダクトとして破綻する。

設計書の案(c)（ストレス90以上でLv5固定）を、全レベルに一般化したもの。
下限なので、フェーズ2以降で睡眠・拘束が加わり予算が下がった場合は、そちらが優先される。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import levels, suggestions, thresholds
from .budget import BudgetResult, DailyContext, Factor, energy_budget

# 内訳に載せる下限。0.5未満は表示すると0点に丸められ、意味のない行になる
_MIN_VISIBLE_COST = 0.5


@dataclass(frozen=True)
class Suggestion:
    id: str
    text: str
    reason: str


@dataclass(frozen=True)
class DailyPlan:
    energy_budget: int
    level: int
    level_name: str
    headline: str
    suggest_title: str
    breakdown: list[Factor]
    suggestions: list[Suggestion]
    # レベルが予算ではなく気圧ストレスの下限で決まったか。
    # 「今日は気圧のせい」と言い切ってよい日かどうかの判定に使う
    level_driven_by_pressure: bool


def budget_to_level(budget: int) -> int:
    """体力予算を省エネレベルへ写像する。"""
    for entry in levels_by_budget():
        if budget >= entry["min_budget"]:
            return int(entry["level"])
    return 5


def levels_by_budget() -> list[dict[str, Any]]:
    """レベル境界を min_budget の降順で返す（Lv1から順に判定するため）。"""
    return sorted(thresholds()["levels"], key=lambda x: x["min_budget"], reverse=True)


def stress_to_level_floor(stress_score: float) -> int:
    """気圧ストレスが単独で要求するレベルの下限を返す。該当が無ければ1。"""
    # min_stress の降順に見て、最初に超えたものを採る
    for entry in sorted(thresholds()["stress_level_floor"], key=lambda x: x["min_stress"], reverse=True):
        if stress_score >= entry["min_stress"]:
            return int(entry["level"])
    return 1


def resolve_level(budget: int, stress_score: float) -> tuple[int, bool]:
    """最終的な省エネレベルと、それが気圧側で決まったかを返す。"""
    from_budget = budget_to_level(budget)
    from_stress = stress_to_level_floor(stress_score)
    return max(from_budget, from_stress), from_stress > from_budget


def level_info(level: int) -> dict[str, Any]:
    """レベルの呼称と文言を引く。"""
    for entry in levels():
        if int(entry["level"]) == level:
            return entry
    raise ValueError(f"未定義の省エネレベルです: {level}")


def pick_suggestions(level: int) -> list[Suggestion]:
    """提案を選ぶ（§4.3）。

    - そのレベル以下の負荷を持つプールからのみ選ぶ（load >= level が「以下の負荷」。上振れ禁止）
    - 1日に提示するのは最大3件。多いこと自体が負荷になるため
    - レベル5では1件のみ
    """
    pool = [s for s in suggestions() if int(s["load"]) >= level]

    if level >= 5:
        # 何もしないことが本日の目標。1件だけ出す
        pool = [s for s in pool if int(s["load"]) >= 5][:1]
        return [Suggestion(id=s["id"], text=s["text"], reason=s["reason"]) for s in pool]

    # load の昇順 = 重い順。そのレベルで許される上限に近いものから選ぶ。
    # 軽い順に選ぶと全レベルで「何もしない」が筆頭になり、レベルの差が消えるため
    # （モックアップ実装時に判明した不具合）
    ordered = sorted(pool, key=lambda s: int(s["load"]))[:3]
    return [Suggestion(id=s["id"], text=s["text"], reason=s["reason"]) for s in ordered]


def build_plan(ctx: DailyContext) -> DailyPlan:
    """体力予算からその日のプランを組み立てる。"""
    result: BudgetResult = energy_budget(ctx)
    level, by_pressure = resolve_level(result.budget, ctx.stress.score)
    info = level_info(level)

    return DailyPlan(
        energy_budget=result.budget,
        level=level,
        level_name=info["name"],
        headline=info["headline"],
        suggest_title=info["suggest_title"],
        breakdown=[f for f in result.factors if f.cost >= _MIN_VISIBLE_COST],
        suggestions=pick_suggestions(level),
        level_driven_by_pressure=by_pressure,
    )
