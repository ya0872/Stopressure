# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

This repository holds the design for **低気圧のすゝめ (Atmosphere Studio)** — see `docs/design.md`.
There is no source code, build system, package manifest, or test suite yet.

Read `docs/design.md` before writing any code. It fixes non-obvious product constraints that are not
inferable from the code, most importantly: the app must never surface streaks, carry-over tasks,
comparisons, nudging notifications, or suggestions that increase load. Those are product-level
prohibitions, not stylistic preferences.

Once code is added to this repository, update this file with:
- Build, lint, and test commands (including how to run a single test)
- High-level architecture notes that require reading multiple files to understand
