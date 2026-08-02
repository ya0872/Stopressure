"""YAML設定の読み込み。

**キャッシュは更新時刻(mtime)で無効化する。** 素の lru_cache だと、プロセスが生きている
あいだ編集が一切反映されない。uvicorn --reload が監視するのは既定で *.py だけなので、
levels.yaml を書き換えてもサーバーは再起動せず、画面には**起動した時点の内容**が出続ける。

2026-08-02 に実際に起きた: 稼働中のAPIは Lv1 を「平常運転」と返し続け、levels.yaml には
「おだやか」と書いてある、という食い違いになった。ファイルを見てもコードを見ても正しいので、
原因がプロセス側にあると気づくまで遠回りする。「YAMLを直したのに画面が変わらない」は
まずこれを疑う（docs/yaml-not-reflected-2026-08-02.txt）。

mtime をキャッシュキーに含めれば、保存した瞬間に別のキーになり読み直される。stat(2) は
毎回走るが、YAMLのパースは変更時だけなので実質のコストはほとんど変わらない。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CONFIG_DIR = Path(__file__).resolve().parent          # backend/app/config
_DATA_DIR = _CONFIG_DIR.parent.parent / "data"         # backend/data


@lru_cache(maxsize=8)
def _load_yaml(path: Path, mtime_ns: int) -> Any:
    """YAMLを読む。

    mtime_ns はキャッシュのキーにするためだけの引数で、本文では使わない。
    ファイルを書き換えると値が変わるため、別のキーとして読み直される。
    """
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read(path: Path) -> Any:
    """更新時刻を見てから読む。内容が変わっていなければキャッシュが返る。"""
    return _load_yaml(path, path.stat().st_mtime_ns)


def thresholds() -> dict[str, Any]:
    """気圧ストレスと体力予算のしきい値。"""
    return _read(_CONFIG_DIR / "thresholds.yaml")


def levels() -> list[dict[str, Any]]:
    """省エネレベルの文言。level の昇順で返す。"""
    return sorted(_read(_DATA_DIR / "levels.yaml"), key=lambda x: x["level"])


def suggestions() -> list[dict[str, Any]]:
    """省エネ提案のプール。"""
    return _read(_DATA_DIR / "suggestions.yaml")


def reload() -> None:
    """キャッシュを明示的に捨てる。

    通常は mtime の変化で足りるので呼ぶ必要はない。同じ mtime のままファイルを
    差し替えた場合（テストでの一時ファイル生成など）のための出口として残してある。
    """
    _load_yaml.cache_clear()
