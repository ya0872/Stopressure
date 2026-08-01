"""テスト共通の前処理。

実行のたびに一時DBへ差し替える。開発中のDB（backend/data/app.db）にテストの書き込みが
混ざると、保存済み設定や吐き出し履歴を壊すため。

気象とGoogleの取得結果はプロセス内にキャッシュされる。テスト間で持ち越すと、
差し替えたはずのデータが使われず、通ったように見えてしまうので毎回捨てる。
"""
from __future__ import annotations

import pytest

from app import db
from app.services import google_client, open_meteo


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """全テストでDBを一時ディレクトリに向け、キャッシュを初期化する。"""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    open_meteo.clear_cache()
    google_client.clear_context_cache()
    yield
    open_meteo.clear_cache()
    google_client.clear_context_cache()
