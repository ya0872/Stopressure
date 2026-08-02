"""SQLiteへの接続とスキーマ初期化。

単一ユーザーのローカル運用のため、サーバープロセスを持たないSQLiteで十分。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

# --- スキーマ定義 -------------------------------------------------------------
# app_setting は「平文で持ってよい設定」と「暗号化が必要な設定」を1テーブルで扱う。
# value と encrypted のどちらか一方だけを使う。
_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_setting (
    key        TEXT PRIMARY KEY,
    value      TEXT,         -- 平文で良い設定（モデル名など）
    encrypted  BLOB,         -- 機微な設定（APIキー）
    updated_at TEXT NOT NULL
);

-- 夜の吐き出しの記録。felt は体感（1:つらい 2:普通 3:平気）で、F-15の学習に使う
CREATE TABLE IF NOT EXISTS reflection (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    date       TEXT NOT NULL,
    user_text  TEXT NOT NULL,
    reply_text TEXT NOT NULL,
    level      INTEGER,
    felt       INTEGER,
    created_at TEXT NOT NULL
);

-- 気象スナップショット。API障害時のフォールバックと、しきい値チューニングの検証に使う。
-- latitude/longitude は設計書 §6 に無いが、別の都市の値でフォールバックしないために必要。
-- raw_json にはストレス指数を再計算できるだけの時系列（過去24h〜予報12h）を入れる。
CREATE TABLE IF NOT EXISTS atmosphere_snapshot (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at  TEXT NOT NULL,
    latitude     REAL NOT NULL,
    longitude    REAL NOT NULL,
    pressure     REAL NOT NULL,
    temperature  REAL,
    humidity     REAL,
    stress_score REAL NOT NULL,
    source       TEXT NOT NULL,   -- 'open-meteo' | 'jma'
    raw_json     TEXT
);

-- フォールバックは常に「直近のもの」を引くため、地点で絞ってからid降順で走査する
CREATE INDEX IF NOT EXISTS idx_snapshot_location
    ON atmosphere_snapshot (latitude, longitude, id DESC);

-- OAuthトークン。平文保存を避けFernetで暗号化する（docs/design.md §7.2）。
-- encrypted には Credentials.to_json() の暗号文が入る。refresh_token を含むため、
-- ここが漏れるとカレンダーとメールのメタデータに継続的にアクセスされる。
CREATE TABLE IF NOT EXISTS oauth_token (
    provider   TEXT PRIMARY KEY,   -- 'google'
    encrypted  BLOB NOT NULL,
    expires_at TEXT,
    updated_at TEXT NOT NULL
);

-- 対話機能の利用回数（依存防止 / F-16、docs/design.md §4.8）。
-- フロント側のブロックはリロードで消え、:8000 を直接叩けば迂回できるため、
-- 強制力はここに置く。services/usage_limit.py だけがこのテーブルを触る。
--
-- date はローカル日付である点に注意。他テーブルはUTCで記録しているが、フェーズが
-- 「生活時間の6時間区切り」である以上、UTCで数えると9時間ずれて深夜帯が前日に混ざる。
CREATE TABLE IF NOT EXISTS usage_counter (
    date       TEXT NOT NULL,      -- ローカル日付 'YYYY-MM-DD'
    phase      INTEGER NOT NULL,   -- 0..3（0時/6時/12時/18時 起点）
    endpoint   TEXT NOT NULL,      -- 'generate' | 'reflection'
    count      INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (date, phase, endpoint)
);
"""


def get_conn() -> sqlite3.Connection:
    """接続を返す。呼び出し側で close すること。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """起動時にスキーマを作成する。既存テーブルがあれば何もしない。"""
    conn = get_conn()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
