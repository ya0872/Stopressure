"""APIキーなど機微な値を暗号化して保存するための共通処理。

平文のまま保存すると、DBファイルを覗くだけでキーが漏れる。Fernet（AES128-CBC + HMAC）で
暗号化して保存し、復号は必要な瞬間だけ行う。
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

# 暗号鍵の保存先。環境変数 TOKEN_ENCRYPTION_KEY が優先され、無ければ自動生成する
_KEY_FILE = Path(__file__).resolve().parent.parent / ".secret.key"


def _load_key() -> bytes:
    """暗号鍵を取得する。存在しなければ生成して保存する。"""
    env_key = os.getenv("TOKEN_ENCRYPTION_KEY")
    if env_key:
        return env_key.encode()

    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes()

    # 初回起動時に生成する。この鍵を失うと保存済みのAPIキーは復号できない
    key = Fernet.generate_key()
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _KEY_FILE.write_bytes(key)
    try:
        os.chmod(_KEY_FILE, 0o600)  # Windowsでは効果がないが害もない
    except OSError:
        pass
    return key


def _fernet() -> Fernet:
    return Fernet(_load_key())


def encrypt(plain: str) -> bytes:
    """平文を暗号化する。"""
    return _fernet().encrypt(plain.encode())


def decrypt(token: bytes | None) -> str | None:
    """暗号文を復号する。鍵が変わっているなど復号できない場合は None を返す。"""
    if not token:
        return None
    try:
        return _fernet().decrypt(token).decode()
    except (InvalidToken, ValueError):
        # 鍵を紛失・変更した場合。呼び出し側では「未設定」として扱わせる
        return None


def mask(secret: str, head: int = 6, tail: int = 4) -> str:
    """APIキーを画面表示用にマスクする。例: AIzaSy…3f9c

    平文をAPIレスポンスに含めないため、確認用にはこの形式だけを返す。
    """
    if len(secret) <= head + tail:
        return "…" * 4
    return f"{secret[:head]}…{secret[-tail:]}"
