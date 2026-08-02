"""対話機能の利用状況を返す（F-16 / docs/design.md §4.8）。

フロント側のカウンタはリロードで 0 に戻るため、これが無いと「画面は使えるのに叩くと429」
という状態になる。起動時と復帰時にここを引いて表示を合わせるためのエンドポイント。

**回数は返さない。** 「あと3回」と表示できてしまうとカウントダウンの圧力になり、
§1.2 が禁じるカウント表示にあたる。出すのは「今使えるか」と「次にいつ使えるか」だけ。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services import usage_limit

router = APIRouter(prefix="/usage", tags=["usage"])


class EndpointUsage(BaseModel):
    blocked: bool = Field(description="この機能が今使えない状態か")


class UsageResponse(BaseModel):
    blocked: bool = Field(description="対話機能がすべて使えない状態か")
    resets_at: datetime = Field(description="次のフェーズが始まる時刻")
    message: str | None = Field(default=None, description="blocked のとき画面に出す文")
    endpoints: dict[str, EndpointUsage]


@router.get("", response_model=UsageResponse)
def get_usage() -> UsageResponse:
    """現在のフェーズにおける利用状況を返す。カウントは増やさない。"""
    statuses = usage_limit.snapshot()

    # 一部だけ尽きている状態で全面ブロックにはしない。
    # 献立の枠が尽きても、夜の吐き出しはまだ受け取れる（§4.8「制限するのは対話機能のみ」）
    all_blocked = all(s.blocked for s in statuses.values())
    resets_at = usage_limit.next_phase_at()

    return UsageResponse(
        blocked=all_blocked,
        resets_at=resets_at,
        message=(
            f"今日はもう十分に確認しました。{resets_at.strftime('%H:%M')}ごろに、またお聞きします。"
            if all_blocked
            else None
        ),
        endpoints={name: EndpointUsage(blocked=s.blocked) for name, s in statuses.items()},
    )
