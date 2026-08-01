"""Google OAuth の認可フローと設定APIの検証（docs/design.md §7.2）。

Googleへは接続しない。認可URLの組み立てはローカル処理なので実物を使い、
トークン交換だけを差し替える。
"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app import oauth_store, settings_store as store
from app.main import app
from app.services import google_client, google_oauth

client = TestClient(app)

DUMMY_TOKEN = json.dumps({
    "token": "ya29.dummy-access-token",
    "refresh_token": "1//dummy-refresh-token",
    "client_id": "dummy.apps.googleusercontent.com",
    "client_secret": "dummy-secret",
    "token_uri": "https://oauth2.googleapis.com/token",
    "scopes": google_oauth.SCOPES,
})


@pytest.fixture
def configured():
    """OAuthクライアントを登録済みの状態にする。"""
    store.set_plain(store.KEY_GOOGLE_CLIENT_ID, "dummy.apps.googleusercontent.com")
    store.set_secret(store.KEY_GOOGLE_CLIENT_SECRET, "dummy-secret")
    google_oauth._pending_states.clear()


@pytest.fixture
def linked(configured):
    """連携済みの状態にする。"""
    oauth_store.save(oauth_store.PROVIDER_GOOGLE, DUMMY_TOKEN, "2026-08-01T15:00:00+00:00")


# --- 設定API ------------------------------------------------------------------

def test_status_before_setup():
    body = client.get("/api/v1/settings/google").json()
    assert body["configured"] is False
    assert body["linked"] is False
    assert body["login_url"] == "/api/v1/auth/google/login"


def test_scopes_are_read_only_and_minimal():
    """要求する権限が読み取り専用で、メール本文を含まないこと。

    gmail.readonly を要求すると本文まで読めてしまい、§7.2 の判断が崩れる。
    スコープの追加を防ぐための回帰テスト。
    """
    scopes = client.get("/api/v1/settings/google").json()["scopes"]

    assert set(scopes) == {
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/gmail.metadata",
        "https://www.googleapis.com/auth/tasks.readonly",
    }
    for forbidden in ("gmail.readonly", "gmail.modify", "mail.google.com", "calendar.events"):
        assert not any(forbidden in s for s in scopes), f"{forbidden} を要求してはいけない"


def test_client_secret_is_never_returned(configured):
    """client_secret を平文で返す経路を作らないこと。"""
    body = client.get("/api/v1/settings/google").json()
    assert "client_secret" not in body
    assert "dummy-secret" not in json.dumps(body)


def test_token_is_never_returned(linked):
    """保存済みトークンを返す経路を作らないこと。"""
    for path in ("/api/v1/settings/google", "/api/v1/context"):
        body = json.dumps(client.get(path).json())
        assert "ya29." not in body
        assert "1//dummy-refresh-token" not in body


def test_update_and_unlink(configured):
    res = client.put("/api/v1/settings/google", json={"use_context": False})
    assert res.status_code == 200
    assert res.json()["use_context"] is False

    oauth_store.save(oauth_store.PROVIDER_GOOGLE, DUMMY_TOKEN)
    assert client.get("/api/v1/settings/google").json()["linked"] is True

    res = client.delete("/api/v1/settings/google")
    assert res.json()["linked"] is False
    assert oauth_store.load(oauth_store.PROVIDER_GOOGLE) is None


def test_empty_update_is_rejected():
    assert client.put("/api/v1/settings/google", json={}).status_code == 400


# --- client_id の形式検査 ------------------------------------------------------
# 実際に、空白と @ が混入した client_id が保存され、Googleが 401 invalid_client を
# 返す事故が起きた。Google側のメッセージは「クライアントが見つからない」だけで
# 原因が分からないため、保存の時点で弾く。

VALID_CLIENT_ID = "123456789012-abcdefghijklmnopqrstuvwxyz012345.apps.googleusercontent.com"


def test_valid_client_id_is_accepted():
    res = client.put("/api/v1/settings/google", json={"client_id": VALID_CLIENT_ID})
    assert res.status_code == 200
    assert res.json()["client_id"] == VALID_CLIENT_ID


@pytest.mark.parametrize("bad,hint", [
    ("1030352529567-  02h2sas990fb.apps.googleusercontent.com", "空白"),          # 実際に起きた事故
    ("123456789012-abc@def.apps.googleusercontent.com", "使えない文字"),
    ("123456789012-abcdef.apps.googleusercontent.co", "末尾"),
    ("123456789012-ABCDEF.apps.googleusercontent.com", "大文字"),
    ("not-a-client-id-at-all", "末尾"),
])
def test_malformed_client_id_is_rejected(bad, hint):
    res = client.put("/api/v1/settings/google", json={"client_id": bad})
    assert res.status_code == 422
    assert hint in json.dumps(res.json(), ensure_ascii=False)


def test_malformed_client_id_is_not_saved(configured):
    """検査に落ちた値で既存の設定を壊さないこと。"""
    before = client.get("/api/v1/settings/google").json()["client_id"]
    client.put("/api/v1/settings/google", json={"client_id": "123456789012-a b c.apps.googleusercontent.com"})
    assert client.get("/api/v1/settings/google").json()["client_id"] == before


def test_client_secret_with_whitespace_is_rejected():
    res = client.put("/api/v1/settings/google", json={"client_secret": "GOCSPX-abc def"})
    assert res.status_code == 422
    assert "空白" in json.dumps(res.json(), ensure_ascii=False)


# --- client_id と client_secret の組み合わせ検証 -------------------------------
# シークレットの誤りは、これが無いと「認可は通るのにトークン交換で落ちる」という
# 分かりにくい形でしか出ない（実際にそれで詰まった）。

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_verify_client_accepts_matching_secret(configured, monkeypatch):
    """invalid_grant が返れば、ID とシークレットの組み合わせは受理されている。"""
    monkeypatch.setattr(
        "httpx.post",
        lambda *a, **k: _FakeResponse({"error": "invalid_grant", "error_description": "Bad Request"}),
    )
    res = client.post("/api/v1/settings/google/test")

    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_verify_client_detects_wrong_secret(configured, monkeypatch):
    monkeypatch.setattr(
        "httpx.post",
        lambda *a, **k: _FakeResponse({
            "error": "invalid_client",
            "error_description": "The provided client secret is invalid.",
        }),
    )
    res = client.post("/api/v1/settings/google/test")

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "一致しません" in body["message"]


def test_verify_client_requires_registration():
    res = client.post("/api/v1/settings/google/test")
    assert res.status_code == 200
    assert res.json()["ok"] is False
    assert "未登録" in res.json()["message"]


def test_verify_client_reports_network_failure(configured, monkeypatch):
    """学内プロキシ等で到達できない場合も、原因をそのまま見せる。"""
    def boom(*a, **k):
        raise RuntimeError("proxy timeout")

    monkeypatch.setattr("httpx.post", boom)
    res = client.post("/api/v1/settings/google/test")

    assert res.status_code == 200
    assert res.json()["ok"] is False
    assert "接続できませんでした" in res.json()["message"]


def test_surrounding_whitespace_is_trimmed():
    """前後の空白は貼り付け事故が多いので落とす。"""
    res = client.put("/api/v1/settings/google", json={"client_id": f"  {VALID_CLIENT_ID}  "})
    assert res.status_code == 200
    assert res.json()["client_id"] == VALID_CLIENT_ID


# --- 認可フロー ---------------------------------------------------------------

def test_login_requires_client_registration():
    """OAuthクライアント未登録なら409。回避手段が無いことを明示する（§7.2）。"""
    res = client.get("/api/v1/auth/google/login", follow_redirects=False)
    assert res.status_code == 409
    assert "Google Cloud Console" in res.json()["detail"]


def test_login_redirects_to_google(configured):
    res = client.get("/api/v1/auth/google/login", follow_redirects=False)
    assert res.status_code == 302

    url = urlparse(res.headers["location"])
    q = parse_qs(url.query)
    assert url.netloc == "accounts.google.com"
    # refresh_token を得るために必須。無いと1時間で連携が切れる
    assert q["access_type"] == ["offline"]
    assert q["prompt"] == ["consent"]
    assert q["redirect_uri"][0].endswith("/api/v1/auth/google/callback")
    assert q["state"][0] in google_oauth._pending_states


def test_callback_rejects_unknown_state(configured):
    """自分が発行していない state は受け付けない（CSRF対策）。"""
    res = client.get("/api/v1/auth/google/callback", params={"code": "x", "state": "forged"})
    assert res.status_code == 400
    assert "state" in res.text


def test_callback_handles_user_denial(configured):
    """同意画面で拒否された場合もエラーにせず、状況を伝える。"""
    res = client.get("/api/v1/auth/google/callback", params={"error": "access_denied"})
    assert res.status_code == 400
    assert "access_denied" in res.text


def test_callback_stores_token(configured, monkeypatch):
    """認可コードを交換してトークンを保存すること。"""
    class FakeCreds:
        expiry = None

        def to_json(self):
            return DUMMY_TOKEN

    class FakeFlow:
        credentials = FakeCreds()
        code_verifier = None

        def fetch_token(self, code=None):
            assert code == "auth-code-123"

    # 認可URLの組み立ては実物を使い、state を得てからトークン交換だけ差し替える
    login = client.get("/api/v1/auth/google/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

    monkeypatch.setattr(google_oauth, "_flow", lambda uri, state=None: FakeFlow())
    res = client.get("/api/v1/auth/google/callback", params={"code": "auth-code-123", "state": state})

    assert res.status_code == 200
    assert "連携しました" in res.text
    assert oauth_store.load(oauth_store.PROVIDER_GOOGLE).payload == DUMMY_TOKEN
    # 使い終わった state は再利用できない
    assert state not in google_oauth._pending_states


# --- PKCE の code_verifier ------------------------------------------------------
# Flow を作り直すと verifier も作り直される。認可時の値を引き継がないと、Googleは
# (invalid_grant) Missing code verifier を返し、連携が必ず失敗する。実際にこれで詰まった。

def test_authorization_url_sends_code_challenge(configured):
    """認可URLに code_challenge が載ること（PKCEが有効であること）。"""
    res = client.get("/api/v1/auth/google/login", follow_redirects=False)
    q = parse_qs(urlparse(res.headers["location"]).query)

    assert "code_challenge" in q
    assert q["code_challenge_method"] == ["S256"]


def test_code_verifier_is_remembered_for_the_exchange(configured):
    """認可時に生成された code_verifier が state と対で保持されること。"""
    res = client.get("/api/v1/auth/google/login", follow_redirects=False)
    state = parse_qs(urlparse(res.headers["location"]).query)["state"][0]

    verifier = google_oauth._pending_states.get(state)
    assert verifier, "code_verifier が保持されていない"
    assert len(verifier) >= 43, "PKCEの検証子として短すぎる"


def test_code_verifier_is_handed_to_the_flow(configured, monkeypatch):
    """トークン交換時、認可時と同じ code_verifier が Flow に渡されること。"""
    class FakeCreds:
        expiry = None

        def to_json(self):
            return DUMMY_TOKEN

    class FakeFlow:
        credentials = FakeCreds()
        code_verifier = "この値が上書きされなければならない"

        def fetch_token(self, code=None):
            pass

    login = client.get("/api/v1/auth/google/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    expected = google_oauth._pending_states[state]

    fake = FakeFlow()
    monkeypatch.setattr(google_oauth, "_flow", lambda uri, state=None: fake)
    client.get("/api/v1/auth/google/callback", params={"code": "x", "state": state})

    assert fake.code_verifier == expected


def test_pending_states_do_not_grow_without_bound(configured):
    """認可を開いて放置した分が無限に溜まらないこと。"""
    for _ in range(google_oauth._MAX_PENDING + 5):
        client.get("/api/v1/auth/google/login", follow_redirects=False)

    assert len(google_oauth._pending_states) <= google_oauth._MAX_PENDING


def test_state_cannot_be_replayed(configured, monkeypatch):
    monkeypatch.setattr(google_oauth, "_flow", lambda uri, state=None: pytest.fail("到達しない"))
    google_oauth._pending_states["used-state"] = "verifier"
    google_oauth._pending_states.pop("used-state")

    res = client.get("/api/v1/auth/google/callback", params={"code": "x", "state": "used-state"})
    assert res.status_code == 400


# --- 未連携でも動くこと --------------------------------------------------------

def test_context_without_link():
    body = client.get("/api/v1/context").json()
    assert body["linked"] is False
    assert body["busy_hours"] is None
    assert body["open_task_count"] is None


def test_current_context_is_empty_when_not_linked():
    """未連携なら例外を投げずに空を返すこと。

    ここで例外が出ると、連携していない利用者の /daily-plan まで落ちる。
    Google連携はフェーズ3の追加機能で、無くてもアプリの核は成立する。
    """
    assert google_client.current_context().any_available is False


def test_use_context_flag_disables_fetch(linked, monkeypatch):
    """反映フラグを切ると、連携済みでも取得しないこと（§7.2 の切替）。"""
    monkeypatch.setattr(
        google_client, "fetch_context",
        lambda creds, now=None: pytest.fail("フラグが無効なのに取得しようとした"),
    )
    client.put("/api/v1/settings/google", json={"use_context": False})

    assert google_client.current_context().any_available is False


def test_broken_token_does_not_break_daily_plan(configured, monkeypatch):
    """トークンが壊れていても /daily-plan は動くこと。"""
    oauth_store.save(oauth_store.PROVIDER_GOOGLE, "{ not json")
    assert google_client.current_context().any_available is False


# --- /daily-plan への反映 ------------------------------------------------------

def test_daily_plan_reflects_google_context(linked, monkeypatch):
    """連携済みなら拘束時間・メール・ToDoが体力予算の内訳に載ること。"""
    from app.services import open_meteo
    from _scenarios import SCENARIOS, hourly_series

    monkeypatch.setattr(open_meteo, "fetch", lambda lat, lon, now=None: hourly_series(SCENARIOS[4]))
    monkeypatch.setattr(google_oauth, "load_credentials", lambda: object())
    monkeypatch.setattr(
        google_client, "fetch_context",
        lambda creds, now=None: google_client.GoogleContext(
            busy_hours=6.0, actionable_mail_count=8, open_task_count=3
        ),
    )

    body = client.get("/api/v1/daily-plan").json()
    names = {b["factor"] for b in body["breakdown"]}

    assert body["google_context_used"] is True
    assert "予定の拘束" in names
    assert "要対応メール・ToDo" in names
    # 秋晴れ（気象の減点0）+ 拘束6時間=12点 + メール8件とToDo3件=11件→上限5点
    assert body["energy_budget"] == 83


def test_google_context_alone_cannot_change_the_level(linked, monkeypatch):
    """Google由来の因子だけでは省エネレベルが動かないことを記録する。

    拘束（上限15）+ メール・ToDo（上限5）= 最大20点。予算は80までしか下がらず、
    レベル1の下限がちょうど80のため、カレンダーが予定で埋まっていても
    気圧か睡眠が絡まない限りレベルは1のまま。

    §4.2.1 と同じ構造の問題で、Google連携は「レベルを動かす機能」ではなく
    「気圧が悪い日の落ち込みを深める機能」として働く。仕様として妥当かは要判断。
    """
    from app.services import open_meteo
    from _scenarios import SCENARIOS, hourly_series

    monkeypatch.setattr(open_meteo, "fetch", lambda lat, lon, now=None: hourly_series(SCENARIOS[4]))
    monkeypatch.setattr(google_oauth, "load_credentials", lambda: object())
    monkeypatch.setattr(
        google_client, "fetch_context",
        # 拘束24時間・メール999件という極端な値を入れても上限で頭打ちになる
        lambda creds, now=None: google_client.GoogleContext(
            busy_hours=24.0, actionable_mail_count=999, open_task_count=999
        ),
    )

    body = client.get("/api/v1/daily-plan").json()
    assert body["energy_budget"] == 80
    assert body["level"] == 1


def test_daily_plan_without_link_has_no_google_factors(monkeypatch):
    """未連携なら Google 由来の因子は内訳に現れないこと（フェーズ1と同じ挙動）。"""
    from app.services import open_meteo
    from _scenarios import SCENARIOS, hourly_series

    monkeypatch.setattr(open_meteo, "fetch", lambda lat, lon, now=None: hourly_series(SCENARIOS[4]))

    body = client.get("/api/v1/daily-plan").json()
    names = {b["factor"] for b in body["breakdown"]}

    assert body["google_context_used"] is False
    assert "予定の拘束" not in names
    assert "要対応メール・ToDo" not in names


def test_context_is_cached(linked, monkeypatch):
    """/daily-plan を開くたびに3つのAPIを叩かないこと。"""
    calls = {"n": 0}

    def counting(creds, now=None):
        calls["n"] += 1
        return google_client.GoogleContext(busy_hours=1.0)

    monkeypatch.setattr(google_oauth, "load_credentials", lambda: object())
    monkeypatch.setattr(google_client, "fetch_context", counting)

    google_client.current_context()
    google_client.current_context()
    google_client.current_context()

    assert calls["n"] == 1


# --- トークン保存 --------------------------------------------------------------

def test_token_round_trip():
    oauth_store.save(oauth_store.PROVIDER_GOOGLE, DUMMY_TOKEN, "2026-08-01T15:00:00+00:00")
    stored = oauth_store.load(oauth_store.PROVIDER_GOOGLE)

    assert stored.payload == DUMMY_TOKEN
    assert stored.expires_at == "2026-08-01T15:00:00+00:00"


def test_token_is_encrypted_at_rest():
    """DBを直接覗いても refresh_token が読めないこと。"""
    from app.db import get_conn

    oauth_store.save(oauth_store.PROVIDER_GOOGLE, DUMMY_TOKEN)
    conn = get_conn()
    try:
        raw = conn.execute("SELECT encrypted FROM oauth_token WHERE provider = 'google'").fetchone()
    finally:
        conn.close()

    assert b"dummy-refresh-token" not in raw["encrypted"]
    assert b"ya29" not in raw["encrypted"]
