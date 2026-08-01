"""しきい値と提案プールの読み込み。

数値（thresholds.yaml）と文言（levels.yaml / suggestions.yaml）をコードから分離しておく。
F-15（気圧耐性の個人化）で係数を書き換えるとき、ロジックに触れずに済ませるため。

読み込み結果はプロセス内でキャッシュする。ローカル単一ユーザー運用のため、
編集したら再起動する運用でよい（uvicorn --reload なら自動で反映される）。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CONFIG_DIR = Path(__file__).resolve().parent          # backend/app/config
_DATA_DIR = _CONFIG_DIR.parent.parent / "data"         # backend/data


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def thresholds() -> dict[str, Any]:
    """気圧ストレスと体力予算のしきい値。"""
    return _load_yaml(_CONFIG_DIR / "thresholds.yaml")


@lru_cache(maxsize=1)
def levels() -> list[dict[str, Any]]:
    """省エネレベルの文言。level の昇順で返す。"""
    return sorted(_load_yaml(_DATA_DIR / "levels.yaml"), key=lambda x: x["level"])


@lru_cache(maxsize=1)
def suggestions() -> list[dict[str, Any]]:
    """省エネ提案のプール。"""
    return _load_yaml(_DATA_DIR / "suggestions.yaml")


def reload() -> None:
    """キャッシュを捨てる。テストとホットリロード用。"""
    thresholds.cache_clear()
    levels.cache_clear()
    suggestions.cache_clear()
