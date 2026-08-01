"""OAuthトークンの保存と取り出し（docs/design.md §7.2）。

settings_store と分けてあるのは、扱う値の危険度が違うため。
APIキーは失効させれば済むが、refresh_token が漏れるとカレンダーとメールのメタデータへ
継続的にアクセスされる。取り出す経路をこのファイルだけに閉じ、APIから平文を返さない。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from . import crypto
from .db import get_conn

PROVIDER_GOOGLE = "google"


@dataclass(frozen=True)
class StoredToken:
    payload: str            # Credentials.to_json() の中身（復号済み）
    expires_at: str | None
    updated_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save(provider: str, payload: str, expires_at: str | None = None) -> None:
    """トークンを暗号化して保存する。既存があれば置き換える。"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO oauth_token (provider, encrypted, expires_at, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(provider) DO UPDATE SET "
            "  encrypted = excluded.encrypted, "
            "  expires_at = excluded.expires_at, "
            "  updated_at = excluded.updated_at",
            (provider, crypto.encrypt(payload), expires_at, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def load(provider: str) -> StoredToken | None:
    """保存済みトークンを復号して返す。

    暗号鍵を失っている場合は None を返す。呼び出し側では「未連携」として扱わせ、
    再連携を促す（鍵の再生成でトークンが読めなくなるのは復旧可能な事故）。
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT encrypted, expires_at, updated_at FROM oauth_token WHERE provider = ?",
            (provider,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None
    payload = crypto.decrypt(row["encrypted"])
    if payload is None:
        return None
    return StoredToken(payload=payload, expires_at=row["expires_at"], updated_at=row["updated_at"])


def delete(provider: str) -> None:
    """トークンを削除する（連携解除）。"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM oauth_token WHERE provider = ?", (provider,))
        conn.commit()
    finally:
        conn.close()


def exists(provider: str) -> bool:
    """トークンが保存されているか。復号できるかまでは見ない。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM oauth_token WHERE provider = ?", (provider,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()
