"""対話機能の利用回数を記録し、上限を超えたら遮断する（F-16 / docs/design.md §4.8）。

フロントエンド（frontend/src/Dashboard.tsx の useGentleBlock）にも同じ趣旨のブロックが
あるが、あちらは React の state だけで持っているためリロードで消え、curl で :8000 を
直接叩けば迂回できる。**強制力を持つのはこのモジュールだけで、フロント側は表示にすぎない**。

制限するのは対話機能（Geminiを呼ぶ2本）に限る。省エネ度の閲覧は常時できなければ
ならないため、/atmosphere・/daily-plan・/context はこのモジュールを通さない（§4.8）。

「制限」という語をUIに出さない（罰として受け取られるため）という制約があるので、
外へ出す文言は「またあとで聞きます」という言い回しに寄せてある。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..config import thresholds
from ..db import get_conn

logger = logging.getLogger(__name__)

# 1日を4つに割る。6時間ごとで 0時/6時/12時/18時 が各フェーズの起点になる
PHASE_HOURS = 6

# このモジュールが管理する対象。ここに無いものは制限しない
ENDPOINTS = ("generate", "reflection")

# 開発時に上限を上書きするための環境変数の接頭辞。
# 例: USAGE_LIMIT_REFLECTION=50
#
# thresholds.yaml の値は本番の設定であり、開発の都合で書き換えると
# 戻し忘れがそのままコミットに乗って依存防止（F-16）が黙って無効になる。
# 環境変数なら backend/.env（.gitignore 済み）に置けるので、その事故が起きない。
#
# ただし .env に置き忘れると今度は**手元だけ静かに無効**になる。それが分かるよう、
# 上書きが効いている間は起動後の初回だけ WARNING を出す（毎回出すとログが埋まる）。
ENV_LIMIT_PREFIX = "USAGE_LIMIT_"

# 上書きを告知済みの (endpoint, 値)。同じ内容を繰り返し出さないためだけのもの
_announced_overrides: set[tuple[str, int]] = set()


class UsageLimitExceeded(Exception):
    """そのフェーズの上限に達している。

    retry_at は次に使えるようになる時刻。message はそのまま利用者に見せてよい文。
    """

    def __init__(self, endpoint: str, retry_at: datetime) -> None:
        self.endpoint = endpoint
        self.retry_at = retry_at
        self.message = (
            f"今日はもう十分に確認しました。{retry_at.strftime('%H:%M')}ごろに、またお聞きします。"
        )
        super().__init__(self.message)


@dataclass(frozen=True)
class UsageStatus:
    """あるエンドポイントの、現在のフェーズにおける利用状況。

    count と limit を持つのは判定のためであって、**画面へ出すためではない**。
    「あと3回」と見せるとカウントダウンの圧力になり、§1.2 が禁じるカウント表示に
    あたる。APIレスポンスへ載せてよいのは blocked と resets_at だけ。
    """

    endpoint: str
    count: int
    limit: int
    blocked: bool
    resets_at: datetime


def _now() -> datetime:
    """ローカル時刻を返す。

    フェーズは「その人の生活時間の6時間区切り」なので、UTCで数えると9時間ずれ、
    深夜のフェーズ0が前日のフェーズ2に混ざる。他テーブルはUTCで記録しているが、
    ここだけは意図的にローカル時刻を使う。テストから差し替えられるよう関数にしてある。
    """
    return datetime.now()


def current_phase(now: datetime | None = None) -> int:
    """0〜3のフェーズ番号を返す。frontend の currentPhase() と同じ定義。"""
    return (now or _now()).hour // PHASE_HOURS


def phase_key(now: datetime | None = None) -> tuple[str, int]:
    """usage_counter の主キーになる (ローカル日付, フェーズ) を返す。"""
    now = now or _now()
    return now.date().isoformat(), current_phase(now)


def next_phase_at(now: datetime | None = None) -> datetime:
    """現在のフェーズが終わる時刻＝次に使えるようになる時刻。"""
    now = now or _now()
    start = now.replace(
        hour=current_phase(now) * PHASE_HOURS, minute=0, second=0, microsecond=0
    )
    # フェーズ3（18時台）なら翌日の0時になる。timedelta が日付を繰り上げる
    return start + timedelta(hours=PHASE_HOURS)


def limit_for(endpoint: str) -> int:
    """設定ファイルから上限回数を引く。環境変数があればそちらを優先する。

    設定漏れを既定値で握り潰すと防御が黙って無効化されるため、その場合は例外にする。
    環境変数が壊れている（数字でない・0以下）場合も同じ理由で無視せず、警告を出して
    設定ファイルの値に戻す。**上書きが効かないより、効いていないと気づけないほうが危ない。**
    """
    conf = (thresholds().get("usage_limit") or {}).get(endpoint)
    if not conf or "per_phase" not in conf:
        raise KeyError(
            f"thresholds.yaml に usage_limit.{endpoint}.per_phase がありません"
        )
    configured = int(conf["per_phase"])

    raw = os.getenv(ENV_LIMIT_PREFIX + endpoint.upper())
    if raw is None:
        return configured

    try:
        override = int(raw)
    except ValueError:
        logger.warning(
            "%s%s の値 %r が数字ではないため無視します（%d回のままです）",
            ENV_LIMIT_PREFIX, endpoint.upper(), raw, configured,
        )
        return configured
    if override < 1:
        logger.warning(
            "%s%s の値 %d は1未満なので無視します（%d回のままです）",
            ENV_LIMIT_PREFIX, endpoint.upper(), override, configured,
        )
        return configured

    if (endpoint, override) not in _announced_overrides:
        _announced_overrides.add((endpoint, override))
        logger.warning(
            "%s の上限を環境変数で %d 回に上書きしています（thresholds.yaml は %d 回）。"
            "開発用の設定です。backend/.env に残っていないか確認してください",
            endpoint, override, configured,
        )
    return override


def peek(endpoint: str, now: datetime | None = None) -> UsageStatus:
    """現在の利用状況を返す。カウントは増やさない。"""
    now = now or _now()
    date, phase = phase_key(now)

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT count FROM usage_counter WHERE date = ? AND phase = ? AND endpoint = ?",
            (date, phase, endpoint),
        ).fetchone()
    finally:
        conn.close()

    count = row["count"] if row else 0
    limit = limit_for(endpoint)
    return UsageStatus(
        endpoint=endpoint,
        count=count,
        limit=limit,
        blocked=count >= limit,
        resets_at=next_phase_at(now),
    )


def ensure_available(endpoint: str, now: datetime | None = None) -> UsageStatus:
    """上限に達していれば UsageLimitExceeded を送出する。

    LLMを呼ぶ前に必ずこれを通すこと。呼び出し側でこれを忘れると防御が無くなる。
    """
    status = peek(endpoint, now)
    if status.blocked:
        raise UsageLimitExceeded(endpoint, status.resets_at)
    return status


def record(endpoint: str, now: datetime | None = None) -> None:
    """1回分加算する。

    **LLMの呼び出しが成功した後に呼ぶ**。先に加算すると、Gemini側の障害（502/503）で
    利用枠だけを失う。読んでから書くと競合するため、UPSERT の1文で加算する。
    """
    now = now or _now()
    date, phase = phase_key(now)

    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO usage_counter (date, phase, endpoint, count, updated_at) "
            "VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT(date, phase, endpoint) DO UPDATE SET "
            "    count = usage_counter.count + 1, updated_at = excluded.updated_at",
            (date, phase, endpoint, now.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def snapshot(now: datetime | None = None) -> dict[str, UsageStatus]:
    """全エンドポイントの状況をまとめて返す。GET /usage 用。"""
    now = now or _now()
    return {endpoint: peek(endpoint, now) for endpoint in ENDPOINTS}
