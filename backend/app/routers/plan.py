"""体力予算・省エネレベル・提案を返す（docs/design.md §5.1 / F-02 / F-03）。

禁止事項（§1.3）に関わる注意:
    - suggestions に完了状態を表すフィールドを足さないこと（チェックボックスの禁止）
    - 連続日数・前日比・繰り越しに類する項目を足さないこと
    レスポンスの形がそのままUIの誘導になるため、ここが最初の防波堤になる。

estimated_capacity（§4.6 / F-17）はフェーズ5かつ未決事項のため、まだ返さない。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services import atmosphere, google_client, planner
from ..services.open_meteo import AtmosphereUnavailable
from .atmosphere import DEFAULT_LAT, DEFAULT_LON

router = APIRouter(prefix="/daily-plan", tags=["plan"])


class BreakdownItem(BaseModel):
    factor: str = Field(description="因子の名前")
    cost: int = Field(description="体力予算から差し引かれた点数")
    cap: int = Field(description="この因子が取りうる最大点数")
    detail: str = Field(description="根拠の説明")


class SuggestionItem(BaseModel):
    # 完了フラグを持たない。完了・未完了の概念を持ち込まないため（§1.3）
    id: str
    text: str
    reason: str


class DailyPlanResponse(BaseModel):
    date: str
    energy_budget: int = Field(description="0〜100。小さいほど余裕がない")
    level: int = Field(description="省エネレベル 1〜5")
    level_name: str
    headline: str
    suggest_title: str
    level_driven_by_pressure: bool = Field(
        description="レベルが体力予算ではなく気圧ストレスの下限で決まったか（§4.2.1）"
    )
    pressure_stress: float
    stale: bool = Field(description="通信に失敗し、保存済みの気象データで代替したか")
    google_context_used: bool = Field(
        description="カレンダー・メール・ToDoを予算に反映したか。未連携なら false"
    )
    breakdown: list[BreakdownItem]
    suggestions: list[SuggestionItem]


@router.get("", response_model=DailyPlanResponse)
def get_daily_plan(
    lat: float = Query(default=DEFAULT_LAT, ge=-90, le=90),
    lon: float = Query(default=DEFAULT_LON, ge=-180, le=180),
) -> DailyPlanResponse:
    """本日の体力予算と省エネレベル、提案を返す。"""
    try:
        obs = atmosphere.current(lat, lon)
    except AtmosphereUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    ctx = atmosphere.to_context(obs)

    # Google連携があれば拘束時間・メール・ToDoを載せる。未連携なら None のままで、
    # 内訳にも現れない（フェーズ1と同じ挙動に落ちる）
    gctx = google_client.current_context()
    ctx.busy_hours = gctx.busy_hours
    ctx.actionable_mail_count = gctx.actionable_mail_count
    ctx.open_task_count = gctx.open_task_count

    plan = planner.build_plan(ctx)

    return DailyPlanResponse(
        # observed_at は "2026-08-01T14:00+09:00" 形式。日付部分だけを取る
        date=obs.observed_at[:10],
        energy_budget=plan.energy_budget,
        level=plan.level,
        level_name=plan.level_name,
        headline=plan.headline,
        suggest_title=plan.suggest_title,
        level_driven_by_pressure=plan.level_driven_by_pressure,
        pressure_stress=round(obs.stress.score, 1),
        stale=obs.stale,
        google_context_used=gctx.any_available,
        breakdown=[
            BreakdownItem(
                factor=f.name, cost=int(round(f.cost)), cap=int(round(f.cap)), detail=f.detail
            )
            for f in plan.breakdown
        ],
        suggestions=[
            SuggestionItem(id=s.id, text=s.text, reason=s.reason) for s in plan.suggestions
        ],
    )
