# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

This repository holds **低気圧のすゝめ (Atmosphere Studio)**: the design document, the screens, and a
FastAPI backend. Done: phase 1 (weather → pressure stress → energy level → suggestions), the Gemini
integration, and the phase-3 Google integration (OAuth + Calendar/Tasks/Gmail). There is no
frontend build yet — the pages under `mockup/` are the only UI, but they now run on live data.

- `docs/design.md` — the design document. **Read it before writing any code.**
- `mockup/index.html` — the product screen. Dependency-free single file, **live data**: it calls
  `/daily-plan`, `/atmosphere`, `/context`, `/settings/google`, `/reflection`, `/settings/gemini`
  and re-fetches every 5 minutes. It computes nothing — level, headline, suggestions and the budget
  breakdown all come from the backend. Degrades to an explanatory notice when the backend is down,
  and to weather-only factors when Google is not linked.
- `mockup/live.html` — raw-value inspection page for the same endpoints. Overlaps index.html now
  that index.html is live; keep it only as long as the flat `/context` + `/settings/google` dump is
  useful for debugging. Not a product screen.
- `mockup/settings.html` — 設定画面 (§8.1). Registers the Gemini API key and the Google OAuth
  client, starts/clears the Google link. Secrets go in via `type=password`, are cleared from the
  field after saving, and are never echoed back — the backend has no endpoint that returns them.
- `backend/` — FastAPI + SQLite. `pytest` from `backend/` runs the suite.

**The scoring algorithm now lives in two places**: `backend/app/services/{pressure,budget,planner}.py`
and `backend/app/config/thresholds.yaml`. It used to be mirrored in JS inside `mockup/index.html`;
that copy was deleted on 2026-08-01 when the page went live, so there is nothing to keep in sync any
more. **Do not reintroduce a JS copy of the scoring rules** — the page is a renderer.
`backend/tests/_scenarios.py` still carries the five weather scenarios (typhoon, rainy, bomb, front,
clear) as test fixtures with pinned stress values; they are no longer mirrored by any UI.

## Product constraints that are not inferable from the code

The app must never surface streaks, carry-over tasks, comparisons, nudging notifications, checkboxes
on suggestions, or suggestions that increase load. These are product-level prohibitions
(`docs/design.md` §1.2), not stylistic preferences — the whole concept collapses if a standard
health-app UI pattern gets implemented by reflex.

The medical disclaimer (`docs/design.md` §1.3) is a required UI element, not optional copy.

## Gemini model selection — a saved model that cannot generate is invisible

Fixed 2026-08-02. Picking a model in `console.html` used to be able to brick the app silently:
`/reflection` would return `200` with `model: null` and a canned reply forever, and nothing in the
UI looked wrong. Three facts make this trap, and none of them are visible from the API:

- **`models.list()` does not tell you what works.** TTS, image, computer-use and omni models all
  advertise `generateContent` in `supported_actions`, yet reject a text-in/text-out call
  (`400 … response modalities (TEXT) is not supported`). `_NON_TEXT_FRAGMENTS` in
  `services/gemini.py` drops them by name. That list is a heuristic and will miss new families.
- **A perfectly valid text model can still be unusable.** The pro tier returns
  `429 RESOURCE_EXHAUSTED` on a free key. No field in the list response predicts this.
- Therefore **`PUT /settings/gemini` verifies before it writes** (`gemini.verify_model` — one real
  call) and returns `400` without touching the DB when it fails. Do not remove that check to "save
  an API call"; the whole failure mode is that a bad value persists and then hides.

Corollary: `routers/reflection.py` must keep logging the swallowed exception. Returning a canned
reply is deliberate (§4.7), but the *reason* has to reach the uvicorn log — with the fallback silent,
"model is null" was the only symptom and it names no cause.

## Usage limiting (F-16) — the block exists twice, but only one copy enforces

Built 2026-08-02 to `docs/design.md` §4.8. Per-phase **call counts**, not the "one hour per phase"
time window the design document described until v0.5 — a time window cannot be judged server-side
without a session concept that reload and multiple tabs would break.

`frontend/src/Dashboard.tsx`'s `useGentleBlock` is **display only**. It lives in React state, so it
resets on reload and is bypassed entirely by hitting `:8000` directly. The enforcement is
`backend/app/services/usage_limit.py` and nowhere else. **When a bypass shows up, fix the backend —
tightening the frontend does not close anything.**

Five rules that look like details but are the feature:

- **`/reflection` never returns 429.** Past the limit it returns 200 with `LIMIT_REACHED_REPLY`,
  saves the text, and does not call Gemini. Rejecting it would recreate the "吐き出したのに無視された"
  experience that the fallback in `routers/reflection.py` exists to prevent. The requirement is *do
  not run the LLM*, which this satisfies. `/generate` is the only endpoint that 429s.
- **Count after a successful generation, never before.** Counting first means a Gemini outage
  (502/503) burns the quota without producing anything.
- **`GET /usage` must not return counts.** `UsageStatus` carries `count`/`limit` for the decision;
  only `blocked` and `resets_at` may leave the process. "あと3回" is the countdown pressure §1.2
  prohibits.
- **Do not add viewing endpoints to `usage_limit.ENDPOINTS`.** `/atmosphere`, `/daily-plan` and
  `/context` must work at all hours — §4.8 limits the conversational features, not the ability to
  check your own condition.
- **`ReflectionResponse.reason` (`limit` | `error` | `null`) is for the developer console, never the
  screen.** Hitting the limit and Gemini failing both return `200` + `fallback: true` +
  `model: null`; without `reason` those are indistinguishable, and the two need opposite responses
  (wait vs. fix the config). It carries no count, so §1.2's ban on "あと3回" still holds. Do not
  render it, and do not add `count`/`limit` alongside it.

`usage_counter.date` is a **local** date while every other table records UTC. Phases are `hour // 6`
of the user's day; counting in UTC shifts the boundary by 9 hours and folds the small hours into the
previous day.

**Testing against the limit**: set `USAGE_LIMIT_REFLECTION=50` (or `USAGE_LIMIT_GENERATE`) in
`backend/.env` and restart uvicorn. Do **not** raise `thresholds.yaml` — that file is the shipped
config and a forgotten edit rides along in a commit, silently disabling F-16. `.env` is gitignored,
so it cannot. A live override logs a WARNING once per process so a forgotten one is visible; a
malformed value (non-numeric, `< 1`) is ignored with a warning rather than crashing or, worse,
becoming a permanent block.

## Resolved: level 5 reachability (§4.2.1)

Decided 2026-08-01. The final level is `max(level from energy budget, level floor from pressure
stress)` — see `docs/design.md` §4.2.1 and `stress_level_floor` in `thresholds.yaml`. It is a
**floor, not an override**: once phase 2/3 factors land, a lower budget still wins.

Do not "simplify" this back to a pure budget threshold. Weather-only days can deduct at most
40+10+10 = 60 points, so a pure budget model cannot reach level 4 or 5 at all in phase 1 — a typhoon
would read as "省エネ (Lv3)".

## Google integration constraints

Built to `docs/design.md` §7.2: `calendar.readonly` + `gmail.metadata` + `tasks.readonly`, all
read-only. Gmail is read via `users.labels.get(id="IMPORTANT")` — only the unread **count** comes
back, never a message list, subject, or ID. `tests/test_google_auth.py` pins the scope set; do not
widen it without a deliberate decision (see below).

OAuth tokens are Fernet-encrypted in `oauth_token` and never returned by any endpoint. Not being
linked is a supported state: every Google-derived factor stays `None` and `/daily-plan` degrades to
phase-1 behaviour. `None` ≠ `0` throughout — `0` means "measured, no load" and shows up in the
breakdown, `None` means "not measured" and does not.

**PKCE**: `_pending_states` maps `state → code_verifier`, not just a set of states. `google-auth-oauthlib`
generates the verifier inside `authorization_url()` and sends its hash as `code_challenge`; the callback
builds a *fresh* `Flow`, so the verifier must be carried across or Google returns
`invalid_grant: Missing code verifier` every time. Do not "simplify" that dict back to a set.

**Debugging 連携できない: read the uvicorn log first, do not reason from the browser message.**
The PKCE bug above surfaced in the UI as `invalid_client`, which points at the credentials and is
wrong. `routers/auth_google.py` logs the real exception with `exc_info=True`. Four real failures and
their guards are recorded in `docs/design.md` §7.2.3.

Credential mistakes are the other setup hazard — Google's errors do not identify the cause.
`POST /api/v1/settings/google/test` verifies the client_id/secret pair without the consent screen
(bogus code → `invalid_grant` means the pair is good, `invalid_client` means the secret is wrong).

## Open decisions

- `docs/design.md` §11 #2 — 推定稼働率 (F-17). Not returned by the API yet, deliberately.
- §11 #10 — Google factors cap at 15 + 5 = 20 points, so the budget bottoms out at 80, which is
  exactly the level-1 boundary. A fully booked calendar alone cannot change the energy level.
- §11 #11 — Gmail summarisation (the requested feature #2) is **not built**. It needs
  `gmail.readonly`, which reverses §7.2's minimal-privilege decision and opens a second path for
  free text to reach Gemini — the thing `tests/test_generate_guard.py` exists to prevent.

## Running it

```powershell
# バックエンド（:8000）
cd backend
python -m uvicorn app.main:app --reload --port 8000

# 画面（:8765）。依存ゼロなのでビルド不要
#   --directory を必ず付ける。付け忘れるとカレントディレクトリを配信し、404になる
#   --bind :: で IPv4/IPv6 両対応になる（http.server は DualStackServer を使うため）
python -m http.server 8765 --directory mockup --bind ::
#   http://localhost:8765/settings.html  APIキー・Google連携の登録
#   http://localhost:8765/live.html      実データ確認
#   http://localhost:8765/index.html     モックアップ（シナリオ切替）

# テスト
cd backend; python -m pytest -q
```

`file://` でも開けるが、ブラウザ拡張から操作する場合は上記のサーバー経由にする。

**`localhost` と `::1` の罠**: Windows のブラウザは `localhost` をまず `::1`（IPv6）に解決する。

- **:8000（uvicorn）は `--host 127.0.0.1` のままでよい。** `::1` は接続拒否になるが、ブラウザは
  即座に IPv4 へフォールバックするので実害がない。`--host ::` にすると **IPv6専用**になり、
  今度は `127.0.0.1` が死ぬ（uvicorn は `IPV6_V6ONLY` を解除しない）。`--host 0.0.0.0` は
  APIキーを持つ設定APIをLANに晒すので使わないこと。
- **:8765（http.server）は `--bind ::` にする。** こちらは `DualStackServer` なので両対応になる。

**「追加したはずのページが404」「古い内容が返る」ときは、まずポートの取り合いを疑う。**
`--directory` を付け忘れたサーバーや、前回の孤児プロセスが `[::]` 側に残っていると、
`localhost`（＝`::1`）のリクエストだけがそちらへ吸われる。netstat では別行に見えるので気づきにくい。

```powershell
# どのプロセスが何を配信しているかを確認する
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
  Select-Object ProcessId, CommandLine | Format-List

# 全部落としてから立て直す
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
  Where-Object { $_.CommandLine -like '*http.server*' -or $_.CommandLine -like '*uvicorn*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

**`--reload` がハングして古いコードを配り続けることがある**: WatchFiles のリローダーを止めても
`multiprocessing.spawn` の子プロセスが孤児として残り、ポート8000を握ったまま**変更前のルートを
返し続ける**。「追加したはずのエンドポイントが404」なら真っ先にこれを疑う。

```powershell
# 孤児プロセスを含めて確実に落とす
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
  Where-Object { $_.CommandLine -like '*uvicorn*' -or $_.CommandLine -like '*multiprocessing-fork*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```


