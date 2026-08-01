"""アプリ設定の読み書き。

機微な値（APIキー）は crypto 経由で暗号化して保存し、平文はDBに残さない。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from . import crypto
from .db import get_conn

# 設定キーの定義
KEY_GEMINI_API = "gemini.api_key"      # 暗号化して保存する
KEY_GEMINI_MODEL = "gemini.model"      # 平文で保存する

# モデル未設定時の既定値。設定画面から変更できる
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_plain(key: str) -> str | None:
    """平文設定を取得する。"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM app_setting WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def set_plain(key: str, value: str) -> None:
    """平文設定を保存する。"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO app_setting (key, value, encrypted, updated_at) VALUES (?, ?, NULL, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_secret(key: str) -> str | None:
    """機微設定を復号して取得する。鍵を失っている場合は None を返す。"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT encrypted FROM app_setting WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return crypto.decrypt(row["encrypted"])


def set_secret(key: str, value: str) -> None:
    """機微設定を暗号化して保存する。"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO app_setting (key, value, encrypted, updated_at) VALUES (?, NULL, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET encrypted = excluded.encrypted, updated_at = excluded.updated_at",
            (key, crypto.encrypt(value), _now()),
        )
        conn.commit()
    finally:
        conn.close()


def delete(key: str) -> None:
    """設定を削除する。"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM app_setting WHERE key = ?", (key,))
        conn.commit()
    finally:
        conn.close()


def resolve_gemini_api_key() -> str | None:
    """有効なGemini APIキーを解決する。

    設定画面で登録した値を優先し、無ければ環境変数 GEMINI_API_KEY を使う。
    開発時は環境変数、通常利用は設定画面という使い分けを想定している。
    """
    return get_secret(KEY_GEMINI_API) or os.getenv("GEMINI_API_KEY") or None


def resolve_gemini_model() -> str:
    """使用するモデル名を解決する。"""
    return get_plain(KEY_GEMINI_MODEL) or DEFAULT_GEMINI_MODEL
