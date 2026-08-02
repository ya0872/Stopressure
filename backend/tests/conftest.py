"""テスト共通の前処理。

実行のたびに一時DBへ差し替える。開発中のDB（backend/data/app.db）にテストの書き込みが
混ざると、保存済み設定や吐き出し履歴を壊すため。

気象とGoogleの取得結果はプロセス内にキャッシュされる。テスト間で持ち越すと、
差し替えたはずのデータが使われず、通ったように見えてしまうので毎回捨てる。

DBを差し替えるだけでは足りない。app/main.py が backend/.env を load_dotenv() で
読むため、手元の .env がそのままテストに漏れる（下の _ISOLATED_ENV を参照）。
"""
from __future__ import annotations

import pytest

from app import db
from app.services import google_client, open_meteo

# テスト実行中は無視する環境変数。
#
# backend/.env は開発用の設定を置く場所で、settings_store の resolve_* 系は
# DBに値が無ければここへフォールバックする。消さないと:
#   - GOOGLE_CLIENT_ID/SECRET があるだけで「クライアント登録済み」と見なされ、
#     未登録前提の test_google_auth.py が落ちる（実際に3件落ちていた）
#   - USAGE_LIMIT_* があると上限がテストごとに変わる。手元の .env の内容で
#     テストの反復回数が変わる状態は、通っていても信用できない
_ISOLATED_ENV = (
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GEMINI_API_KEY",
    "USAGE_LIMIT_GENERATE",
    "USAGE_LIMIT_REFLECTION",
)


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """全テストでDBを一時ディレクトリに向け、環境変数とキャッシュを初期化する。"""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    for name in _ISOLATED_ENV:
        monkeypatch.delenv(name, raising=False)
    db.init_db()
    open_meteo.clear_cache()
    google_client.clear_context_cache()
    yield
    open_meteo.clear_cache()
    google_client.clear_context_cache()
