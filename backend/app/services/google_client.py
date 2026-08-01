"""Google Calendar / Tasks / Gmail から当日の負荷を取得する（F-05 / F-06 / F-18）。

取得するのはすべて「量」であり、内容ではない。

    Calendar → 当日の拘束時間（時間）
    Tasks    → 当日までに期限が来る未完了タスクの件数
    Gmail    → 未読かつ重要なメールの件数

Gmail について:
    users.labels.get で IMPORTANT ラベルの未読件数だけを引く。メッセージ一覧も件名も
    取得しない。件数から精神的負荷を推定するのが目的であり、内容は使わないため（§7.2）。
    この方針により、自由文がGeminiへ渡る経路が増えることもない（§3.3）。

失敗時の方針:
    3つのAPIは独立に失敗しうる。1つ落ちても残りは使えるので、サービスごとに握って
    warnings に積み、取れなかった項目は None のままにする。None は「未計測」として
    体力予算の内訳に現れない（budget.DailyContext の設計）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .open_meteo import JST

# Tasks は複数のリストを持てる。全リストを見るが、暴走を防ぐため上限を設ける
MAX_TASK_LISTS = 10
# 1リストあたりの取得件数上限。体力予算のキャップが5点なので、これ以上数えても結果は変わらない
MAX_TASKS_PER_LIST = 100

# 取得結果のキャッシュ有効期間（秒）。/daily-plan は画面を開くたびに呼ばれるため、
# 都度3つのAPIを叩くと表示が遅くなり、APIクォータも無駄に消費する。
# 予定やメールが5分遅れて反映されても、体力予算の精度には影響しない
CONTEXT_TTL_SEC = 300

_context_cache: tuple[float, "GoogleContext"] | None = None


@dataclass
class GoogleContext:
    """当日の負荷。取得できなかった項目は None。"""
    busy_hours: float | None = None
    actionable_mail_count: int | None = None
    open_task_count: int | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def any_available(self) -> bool:
        return any(v is not None for v in (self.busy_hours, self.actionable_mail_count, self.open_task_count))


# --- 純粋な変換関数（ここだけをテストすれば判定ロジックを担保できる）-----------

def day_window(now: datetime) -> tuple[datetime, datetime]:
    """その日の 00:00〜翌 00:00（JST）を返す。"""
    start = now.astimezone(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _is_declined(event: dict) -> bool:
    """自分が辞退した予定か。辞退した予定は拘束されない。"""
    for a in event.get("attendees") or []:
        if a.get("self") and a.get("responseStatus") == "declined":
            return True
    return False


def busy_hours_from_events(
    events: list[dict], window_start: datetime, window_end: datetime
) -> float:
    """予定リストから当日の拘束時間を算出する。

    除外するもの:
      - 終日予定: 「誕生日」「〜週間」などが24時間の拘束として計上されるのを防ぐ
      - 辞退した予定 / キャンセルされた予定
      - transparency が transparent（Googleカレンダー上「予定あり」にしない設定）の予定

    重なる予定は合算せずマージする。ダブルブッキングを2倍の拘束として数えないため。
    """
    intervals: list[tuple[datetime, datetime]] = []

    for ev in events:
        if ev.get("status") == "cancelled" or ev.get("transparency") == "transparent":
            continue
        if _is_declined(ev):
            continue

        start_raw = (ev.get("start") or {}).get("dateTime")
        end_raw = (ev.get("end") or {}).get("dateTime")
        if not start_raw or not end_raw:
            continue  # 終日予定（date のみ）

        start = datetime.fromisoformat(start_raw).astimezone(JST)
        end = datetime.fromisoformat(end_raw).astimezone(JST)

        # 日をまたぐ予定は当日の範囲だけを数える
        start = max(start, window_start)
        end = min(end, window_end)
        if end > start:
            intervals.append((start, end))

    if not intervals:
        return 0.0

    # 開始順に並べて重なりをマージする
    intervals.sort()
    merged: list[list[datetime]] = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    total = sum((end - start).total_seconds() for start, end in merged)
    return round(total / 3600.0, 2)


def count_due_tasks(tasks: list[dict], today: date) -> int:
    """未完了かつ期限が今日以前のタスク件数を数える。

    期限が無いタスクは数えない。「いつかやる」は今日の負荷ではないため。
    期限切れのタスクは数える。数えることで体力予算が下がり、提案が軽くなる方向に働く
    （§1.3 が禁じるのは繰り越しの「表示」であって、負荷としての勘定ではない）。
    """
    count = 0
    for t in tasks:
        if t.get("status") == "completed" or t.get("deleted"):
            continue
        due_raw = t.get("due")
        if not due_raw:
            continue
        try:
            due = datetime.fromisoformat(due_raw.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if due <= today:
            count += 1
    return count


def unread_important_count(label: dict) -> int:
    """IMPORTANT ラベルの応答から未読件数を取り出す。"""
    return int(label.get("messagesUnread") or 0)


def _service(name: str, version: str, creds):
    """Google API サービスを構築する。

    google-api-python-client は内部で httplib2 を使うが、httplib2 は HTTPS_PROXY を
    自動で読まず、明示的に渡しても学内プロキシ経由で通らない。
    requests ベースの AuthorizedSession を httplib2 互換でラップすることで、
    httpx / requests と同じプロキシ経路を使う。
    """
    import httplib2
    from google.auth.transport.requests import AuthorizedSession
    from googleapiclient.discovery import build

    session = AuthorizedSession(creds)

    class _Http:
        """AuthorizedSession を httplib2.Http 互換にする薄いアダプタ。

        requests は HTTPS_PROXY を自動で読むため、httplib2 のプロキシ問題を回避できる。
        googleapiclient が使う .request(uri, method, body, headers) だけを実装する。
        """
        def request(self, uri, method="GET", body=None, headers=None, **kwargs):
            resp = session.request(method, uri, data=body, headers=headers or {})
            response_headers = {k.lower(): v for k, v in resp.headers.items()}
            response_headers["status"] = str(resp.status_code)
            return httplib2.Response(response_headers), resp.content

    # cache_discovery=False はファイルキャッシュの警告を避けるため
    return build(name, version, http=_Http(), cache_discovery=False)


def fetch_busy_hours(creds, now: datetime) -> float:
    """当日の拘束時間を取得する。"""
    start, end = day_window(now)
    service = _service("calendar", "v3", creds)
    events = service.events().list(
        calendarId="primary",
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,       # 繰り返し予定を実体に展開する
        orderBy="startTime",
        maxResults=250,
    ).execute()
    return busy_hours_from_events(events.get("items") or [], start, end)


def fetch_open_tasks(creds, now: datetime) -> int:
    """期限が今日以前の未完了タスク件数を取得する。"""
    service = _service("tasks", "v1", creds)
    lists = service.tasklists().list(maxResults=MAX_TASK_LISTS).execute()
    today = now.astimezone(JST).date()

    total = 0
    for tl in lists.get("items") or []:
        items = service.tasks().list(
            tasklist=tl["id"],
            showCompleted=False,
            showHidden=False,
            maxResults=MAX_TASKS_PER_LIST,
        ).execute()
        total += count_due_tasks(items.get("items") or [], today)
    return total


def fetch_actionable_mail(creds) -> int:
    """未読かつ重要なメールの件数を取得する。

    users.labels.get はラベルの集計値だけを返す。メッセージIDも件名も取得しない。
    """
    service = _service("gmail", "v1", creds)
    label = service.users().labels().get(userId="me", id="IMPORTANT").execute()
    return unread_important_count(label)


def fetch_context(creds, now: datetime | None = None) -> GoogleContext:
    """3つのAPIから当日の負荷をまとめて取得する。個別の失敗は握って続行する。"""
    now = now or datetime.now(JST)
    ctx = GoogleContext()

    for label, setter in (
        ("カレンダー", lambda: setattr(ctx, "busy_hours", fetch_busy_hours(creds, now))),
        ("ToDo", lambda: setattr(ctx, "open_task_count", fetch_open_tasks(creds, now))),
        ("メール", lambda: setattr(ctx, "actionable_mail_count", fetch_actionable_mail(creds))),
    ):
        try:
            setter()
        except Exception as e:  # googleapiclient の例外型は多岐にわたるため広く捕捉する
            # 落ちた項目だけ None のまま残す。連携全体を失敗にはしない
            ctx.warnings.append(f"{label}の取得に失敗しました: {type(e).__name__}: {e}")

    return ctx


def current_context(now: datetime | None = None) -> GoogleContext:
    """連携済みなら当日の負荷を返す。未連携・未設定・無効時は空の結果を返す。

    Google連携はフェーズ3の追加機能であり、無くてもアプリの核（フェーズ1）は成立する。
    ここで例外を投げると連携していない利用者の /daily-plan まで落ちるため、握って空を返す。
    """
    global _context_cache
    from .. import settings_store as store
    from . import google_oauth

    if not store.google_context_enabled():
        return GoogleContext()

    if _context_cache and (time.monotonic() - _context_cache[0]) < CONTEXT_TTL_SEC:
        return _context_cache[1]

    try:
        creds = google_oauth.load_credentials()
    except (google_oauth.GoogleNotLinked, google_oauth.GoogleNotConfigured):
        # 未連携はキャッシュしない。連携した直後に反映されないと不可解に見えるため
        return GoogleContext()
    except google_oauth.GoogleAuthFailed as e:
        # トークンの更新に失敗した場合。再連携が要ることを伝えたいので警告は残す
        return GoogleContext(warnings=[str(e)])

    ctx = fetch_context(creds, now)
    _context_cache = (time.monotonic(), ctx)
    return ctx


def clear_context_cache() -> None:
    """キャッシュを捨てる。連携解除・設定変更・テスト用。"""
    global _context_cache
    _context_cache = None
