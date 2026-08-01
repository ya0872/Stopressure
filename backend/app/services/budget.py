"""体力予算（docs/design.md §4.2）。

気象以外の負荷因子も統合し、その日に使える体力を0〜100で表現する。
各因子に上限（cap）を設け、単一因子が予算を食い尽くさないようにする。

フェーズ1では気象因子（気圧・気温・湿度）しか取得できない。睡眠(F-04/フェーズ2)、
拘束時間(F-05/フェーズ3)、メール・ToDo(F-06/F-18/フェーズ3)は None を渡すと
内訳に現れない。フェーズ1で最大に引ける点は 40+10+10 = 60 であり、予算だけでは
レベル4・5に到達できない。この不足は planner 側のストレス下限で補う（§4.2.1）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import thresholds
from .pressure import PressureStress


@dataclass(frozen=True)
class Factor:
    """予算から差し引かれた1因子。画面の内訳表示にそのまま使う。"""
    name: str
    cost: float     # 差し引かれた点数
    cap: float      # この因子が取りうる最大点数（バーの目盛りに使う）
    detail: str     # 根拠の説明文


@dataclass
class DailyContext:
    """その日の負荷因子。取得できていない項目は None にする。

    None と 0 を区別するのが重要で、0 は「計測して負荷が無かった」、
    None は「まだ計測していない」を意味する。前者だけを内訳に出す。
    """
    stress: PressureStress
    temp_delta_vs_yesterday: float | None = None   # 前日同時刻比(℃)
    discomfort_index: float | None = None          # 不快指数
    humidity: float | None = None                  # 表示用の湿度(%)
    sleep_hours: float | None = None               # フェーズ2
    busy_hours: float | None = None                # フェーズ3
    actionable_mail_count: int | None = None       # フェーズ3
    open_task_count: int | None = None             # フェーズ3


@dataclass(frozen=True)
class BudgetResult:
    budget: int
    factors: list[Factor] = field(default_factory=list)


def discomfort_index(temp_c: float, humidity_pct: float) -> float:
    """不快指数。気温と湿度から算出する。"""
    return 0.81 * temp_c + 0.01 * humidity_pct * (0.99 * temp_c - 14.3) + 46.3


def energy_budget(ctx: DailyContext) -> BudgetResult:
    """本日の体力予算を算出する（0〜100、小さいほど余裕がない）。"""
    th = thresholds()["energy_budget"]
    factors: list[Factor] = []

    # 気象ストレス（最大 -40）: 中核因子のため重みを最大にする
    weather_cap = 100.0 * th["weather_weight"]
    factors.append(Factor(
        name="気圧の低下",
        cost=ctx.stress.score * th["weather_weight"],
        cap=weather_cap,
        detail=f"6時間で{ctx.stress.delta_6h:+.1f}hPa / 24時間で{ctx.stress.delta_24h:+.1f}hPa",
    ))

    # 気温の前日比（最大 -10）: 5℃以上の変化で身体は消耗する。上昇でも下降でも減点する
    if ctx.temp_delta_vs_yesterday is not None:
        t = th["temp"]
        factors.append(Factor(
            name="気温の変化",
            cost=min(abs(ctx.temp_delta_vs_yesterday) * t["coef"], t["cap"]),
            cap=t["cap"],
            detail=f"前日比 {ctx.temp_delta_vs_yesterday:+.1f}℃",
        ))

    # 不快指数による湿度負荷（最大 -10）
    if ctx.discomfort_index is not None:
        h = th["humid"]
        over = max(ctx.discomfort_index - h["base"], 0.0)
        humid_detail = f"不快指数 {ctx.discomfort_index:.0f}"
        if ctx.humidity is not None:
            humid_detail += f"（湿度{ctx.humidity:.0f}%）"
        factors.append(Factor(
            name="湿度による不快", cost=min(over, h["cap"]), cap=h["cap"], detail=humid_detail,
        ))

    # 睡眠不足（最大 -20）: 7時間を基準に不足1時間あたり5点
    if ctx.sleep_hours is not None:
        s = th["sleep"]
        lack = max(s["ideal"] - ctx.sleep_hours, 0.0)
        factors.append(Factor(
            name="睡眠不足",
            cost=min(lack * s["coef"], s["cap"]),
            cap=s["cap"],
            detail=f"睡眠 {ctx.sleep_hours:.1f}時間",
        ))

    # 予定による拘束（最大 -15）: 拘束1時間あたり2点
    if ctx.busy_hours is not None:
        b = th["busy"]
        factors.append(Factor(
            name="予定の拘束",
            cost=min(ctx.busy_hours * b["coef"], b["cap"]),
            cap=b["cap"],
            detail=f"拘束 {ctx.busy_hours:.1f}時間",
        ))

    # 要対応メール + ToDo（最大 -5）: 1件あたり1点。合算で1つの因子として扱う
    if ctx.actionable_mail_count is not None or ctx.open_task_count is not None:
        m = th["mail"]
        mails = ctx.actionable_mail_count or 0
        tasks = ctx.open_task_count or 0
        factors.append(Factor(
            name="要対応メール・ToDo",
            cost=min((mails + tasks) * m["coef"], m["cap"]),
            cap=m["cap"],
            detail=f"メール{mails}件 / ToDo{tasks}件",
        ))

    total = sum(f.cost for f in factors)
    budget = max(int(round(100.0 - total)), 0)

    # 影響の大きい順に並べる。画面では上から数件しか読まれないため
    factors.sort(key=lambda f: f.cost, reverse=True)
    return BudgetResult(budget=budget, factors=factors)
