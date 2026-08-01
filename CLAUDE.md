# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

This repository holds the design and a working mockup for **低気圧のすゝめ (Atmosphere Studio)**.
There is no backend, build system, package manifest, or test suite yet.

- `docs/design.md` — the design document. **Read it before writing any code.**
- `mockup/index.html` — dependency-free single-file mockup. The scoring logic in it is a direct port
  of `docs/design.md` §4, so changes to the algorithm must be mirrored in both places until the
  FastAPI backend exists.

## Product constraints that are not inferable from the code

The app must never surface streaks, carry-over tasks, comparisons, nudging notifications, checkboxes
on suggestions, or suggestions that increase load. These are product-level prohibitions
(`docs/design.md` §1.2), not stylistic preferences — the whole concept collapses if a standard
health-app UI pattern gets implemented by reflex.

The medical disclaimer (`docs/design.md` §1.3) is a required UI element, not optional copy.

## Open decision blocking implementation

`docs/design.md` §4.2.1 — with the current weights, a typhoon (pressure stress 93/100) only reaches
energy level 4. Level 5 is unreachable from weather alone, which contradicts the product's premise.
Resolve this before building the backend.

## Running the mockup

```powershell
# 依存ゼロなのでビルド不要。ローカルサーバーを立てて開く
python -m http.server 8765 --directory mockup
```

`file://` でも開けるが、ブラウザ拡張から操作する場合は上記のサーバー経由にする。

## Known environment issue: proxy

This machine sits behind the KIT campus proxy `http://wwwproxy-a10.kanazawa-it.ac.jp:8080`.
Raw TCP to the outside fails; only proxied HTTPS gets through. `git push` and `npm install` therefore
time out (`ETIMEDOUT` / `Could not connect to server`) unless the proxy is passed explicitly.

The proxy is NOT discoverable from `git config`, `netsh winhttp show proxy`, or the WinINET registry
keys — all of them report "no proxy". It only shows up via .NET:

```powershell
[System.Net.WebRequest]::GetSystemWebProxy().GetProxy("https://github.com").AbsoluteUri
```

Diagnostic tell: `Test-NetConnection github.com -Port 443` fails while
`Invoke-WebRequest https://github.com` returns 200.

```powershell
# このシェル限りでプロキシ経由にする
$env:HTTPS_PROXY="http://wwwproxy-a10.kanazawa-it.ac.jp:8080"; $env:HTTP_PROXY=$env:HTTPS_PROXY
```

学外ではこのプロキシは使えないため、恒久設定にする場合は解除手順とセットで扱うこと。
