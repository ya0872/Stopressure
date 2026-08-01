"""Google連携から得た当日の負荷を返す（F-05 / F-06 / F-18）。

/daily-plan に統合済みの値をそのまま覗くための入口。フロントエンドが無い段階でも
「連携が効いているか」を確認できるようにしておく。

返すのは件数と時間だけで、予定のタイトル・メールの件名・タスク名は一切含めない。
内容を返す経路を作らないこと自体が §7.2 の方針である。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services import google_client, google_oauth

router = APIRouter(prefix="/context", tags=["context"])


class ContextResponse(BaseModel):
    linked: bool = Field(description="Googleアカウントと連携済みか")
    use_context: bool = Field(description="体力予算への反映が有効か")
    busy_hours: float | None = Field(default=None, description="当日の拘束時間。重なりはマージ済み")
    actionable_mail_count: int | None = Field(default=None, description="未読かつ重要なメールの件数")
    open_task_count: int | None = Field(default=None, description="期限が今日以前の未完了タスク件数")
    warnings: list[str] = Field(default_factory=list, description="個別に取得できなかった項目の理由")


@router.get("", response_model=ContextResponse)
def get_context() -> ContextResponse:
    """当日の拘束時間・メール件数・ToDo件数を返す。"""
    status = google_oauth.status()
    ctx = google_client.current_context()
    return ContextResponse(
        linked=status.linked,
        use_context=status.use_context,
        busy_hours=ctx.busy_hours,
        actionable_mail_count=ctx.actionable_mail_count,
        open_task_count=ctx.open_task_count,
        warnings=ctx.warnings,
    )
