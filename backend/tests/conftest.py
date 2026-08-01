"""テスト共通の前処理。

実行のたびに一時DBへ差し替える。開発中のDB（backend/data/app.db）にテストの書き込みが
混ざると、保存済み設定や吐き出し履歴を壊すため。
"""
from __future__ import annotations

import pytest

from app import db


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """全テストでDBを一時ディレクトリに向ける。"""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    yield
