"""Calendar / Tasks / Gmail の解釈ロジックの検証（docs/design.md §7.2）。

ネットワークには触れない。API応答を解釈する純粋関数だけを対象にする。
判定の誤りはここに出るため、実APIを叩かなくても担保できる。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.services.google_client import (
    GoogleContext,
    busy_hours_from_events,
    count_due_tasks,
    day_window,
    unread_important_count,
)
from app.services.open_meteo import JST

DAY_START = datetime(2026, 8, 1, 0, 0, tzinfo=JST)
DAY_END = DAY_START + timedelta(days=1)


def _event(start: str, end: str, **extra) -> dict:
    ev = {"start": {"dateTime": start}, "end": {"dateTime": end}}
    ev.update(extra)
    return ev


# --- 拘束時間（F-05）----------------------------------------------------------

def test_simple_events_are_summed():
    events = [
        _event("2026-08-01T09:00:00+09:00", "2026-08-01T10:30:00+09:00"),
        _event("2026-08-01T13:00:00+09:00", "2026-08-01T14:00:00+09:00"),
    ]
    assert busy_hours_from_events(events, DAY_START, DAY_END) == 2.5


def test_all_day_events_are_excluded():
    """終日予定は拘束として数えない。

    「誕生日」「〜週間」のような予定が24時間の拘束になると、体力予算が
    毎回ゼロになり、気圧の影響が見えなくなる。
    """
    events = [{"start": {"date": "2026-08-01"}, "end": {"date": "2026-08-02"}}]
    assert busy_hours_from_events(events, DAY_START, DAY_END) == 0.0


def test_declined_events_are_excluded():
    """自分が辞退した予定には拘束されない。"""
    events = [_event(
        "2026-08-01T09:00:00+09:00", "2026-08-01T12:00:00+09:00",
        attendees=[{"self": True, "responseStatus": "declined"}],
    )]
    assert busy_hours_from_events(events, DAY_START, DAY_END) == 0.0


def test_other_peoples_decline_does_not_matter():
    """他人が辞退しても、自分の拘束時間は変わらない。"""
    events = [_event(
        "2026-08-01T09:00:00+09:00", "2026-08-01T10:00:00+09:00",
        attendees=[{"self": False, "responseStatus": "declined"},
                   {"self": True, "responseStatus": "accepted"}],
    )]
    assert busy_hours_from_events(events, DAY_START, DAY_END) == 1.0


def test_transparent_and_cancelled_are_excluded():
    """「予定あり」にしない設定の予定と、キャンセル済みの予定は数えない。"""
    events = [
        _event("2026-08-01T09:00:00+09:00", "2026-08-01T10:00:00+09:00", transparency="transparent"),
        _event("2026-08-01T11:00:00+09:00", "2026-08-01T12:00:00+09:00", status="cancelled"),
    ]
    assert busy_hours_from_events(events, DAY_START, DAY_END) == 0.0


def test_overlapping_events_are_merged():
    """重なる予定を二重に数えない。

    ダブルブッキングは拘束が2倍になるわけではない。合算すると、予定を入れすぎた日に
    体力予算が不当に削られる。
    """
    events = [
        _event("2026-08-01T09:00:00+09:00", "2026-08-01T11:00:00+09:00"),
        _event("2026-08-01T10:00:00+09:00", "2026-08-01T12:00:00+09:00"),
    ]
    assert busy_hours_from_events(events, DAY_START, DAY_END) == 3.0


def test_adjacent_events_are_not_double_counted():
    """連続する予定は境界で結合され、合計は正しく出る。"""
    events = [
        _event("2026-08-01T09:00:00+09:00", "2026-08-01T10:00:00+09:00"),
        _event("2026-08-01T10:00:00+09:00", "2026-08-01T11:00:00+09:00"),
    ]
    assert busy_hours_from_events(events, DAY_START, DAY_END) == 2.0


def test_events_crossing_midnight_are_clipped():
    """日をまたぐ予定は、当日に入る分だけを数える。"""
    events = [_event("2026-07-31T22:00:00+09:00", "2026-08-01T03:00:00+09:00")]
    assert busy_hours_from_events(events, DAY_START, DAY_END) == 3.0


def test_utc_times_are_converted():
    """UTCで返ってきた時刻もJSTに直して扱う。"""
    # 2026-08-01T00:00Z = 09:00 JST
    events = [_event("2026-08-01T00:00:00Z", "2026-08-01T02:00:00Z")]
    assert busy_hours_from_events(events, DAY_START, DAY_END) == 2.0


def test_day_window_is_jst_midnight():
    start, end = day_window(datetime(2026, 8, 1, 15, 30, tzinfo=JST))
    assert start == DAY_START and end == DAY_END


# --- ToDo（F-18）--------------------------------------------------------------

TODAY = date(2026, 8, 1)


def test_counts_tasks_due_today_and_overdue():
    tasks = [
        {"status": "needsAction", "due": "2026-08-01T00:00:00.000Z"},   # 今日
        {"status": "needsAction", "due": "2026-07-28T00:00:00.000Z"},   # 期限切れ
    ]
    assert count_due_tasks(tasks, TODAY) == 2


def test_completed_and_future_tasks_are_ignored():
    tasks = [
        {"status": "completed", "due": "2026-08-01T00:00:00.000Z"},
        {"status": "needsAction", "due": "2026-08-05T00:00:00.000Z"},   # まだ先
        {"status": "needsAction", "due": "2026-08-01T00:00:00.000Z", "deleted": True},
    ]
    assert count_due_tasks(tasks, TODAY) == 0


def test_tasks_without_due_date_are_ignored():
    """期限の無いタスクは今日の負荷ではない。"""
    assert count_due_tasks([{"status": "needsAction", "title": "いつかやる"}], TODAY) == 0


def test_malformed_due_is_skipped():
    """壊れた期限で例外にしない。連携全体が落ちる方が損失が大きい。"""
    assert count_due_tasks([{"status": "needsAction", "due": "not-a-date"}], TODAY) == 0


# --- メール（F-06）------------------------------------------------------------

def test_unread_important_count():
    assert unread_important_count({"id": "IMPORTANT", "messagesUnread": 7}) == 7


def test_missing_unread_field_is_zero():
    assert unread_important_count({"id": "IMPORTANT"}) == 0


# --- 取得結果の扱い ------------------------------------------------------------

def test_empty_context_is_not_available():
    assert GoogleContext().any_available is False


def test_partial_context_is_available():
    """1つでも取れていれば「反映した」と言える。"""
    assert GoogleContext(busy_hours=2.0).any_available is True


@pytest.mark.parametrize("field", ["busy_hours", "actionable_mail_count", "open_task_count"])
def test_failed_field_stays_none(field):
    """取得に失敗した項目は None のまま。0 で埋めない。

    0 は「計測して負荷なし」を意味してしまい、内訳に「予定の拘束 0点」が出る。
    未計測と区別できなくなる（budget.DailyContext の設計）。
    """
    ctx = GoogleContext(warnings=["カレンダーの取得に失敗しました"])
    assert getattr(ctx, field) is None
