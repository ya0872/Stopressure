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

## Known environment issue

npm cannot reach `registry.npmjs.org` from this machine (`ETIMEDOUT`) even though PowerShell can
reach it over HTTPS and no proxy is configured. Workaround to try before assuming npm is unusable:

```powershell
$env:NODE_OPTIONS="--dns-result-order=ipv4first"; npm create vite@latest frontend -- --template react-ts
```
