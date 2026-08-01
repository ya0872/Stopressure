"""生成APIのガードが機能していることを検証する。

docs/design.md §3.3 の「吐き出し内容をGeminiへ送らない」という制約は、
運用ルールではなくコードで担保する必要がある。ここではその担保を検証する。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.generate import GenerateRequest, build_prompt

client = TestClient(app)


def test_reflection_is_routed_to_dedicated_endpoint():
    """吐き出しはこのエンドポイントでは受け付けず、専用の入口へ誘導する。

    自由文を扱う経路を1箇所に閉じ込めるための分離であり、その構造を守るためのテスト。
    """
    res = client.post("/api/v1/generate", json={"purpose": "reflection", "level": 4})
    assert res.status_code == 400
    assert "/api/v1/reflection" in res.json()["detail"]


def test_unknown_purpose_is_rejected():
    """未知の用途は通さない。"""
    res = client.post("/api/v1/generate", json={"purpose": "anything", "level": 3})
    assert res.status_code == 400


def test_request_has_no_free_text_field():
    """リクエストモデルに自由文フィールドが無いこと。

    text や prompt を受け取れてしまうと、ユーザーの入力がGeminiへ届く経路が生まれる。
    フィールドの追加を防ぐための回帰テスト。
    """
    fields = set(GenerateRequest.model_fields.keys())
    assert fields == {"purpose", "level", "template_id", "tone"}
    for forbidden in ("text", "prompt", "content", "message", "user_text"):
        assert forbidden not in fields


@pytest.mark.parametrize("level,keyword", [(4, "調理させない"), (5, "食べないという選択")])
def test_meal_prompt_respects_level(level: int, keyword: str):
    """省エネレベルが高い日は、調理を要求しないプロンプトになる。"""
    _, prompt = build_prompt(GenerateRequest(purpose="meal", level=level))
    assert keyword in prompt


def test_reward_prompt_blocks_exercise_on_low_levels():
    """レベル3以上では運動も外出も許可しない（docs/design.md §1.3）。"""
    _, prompt = build_prompt(GenerateRequest(purpose="reward", level=3))
    assert "体を動かす必要がなく" in prompt
    assert "家から出ずに済む" in prompt

    _, prompt_ok = build_prompt(GenerateRequest(purpose="reward", level=2))
    assert "運動や外出を伴うものも可" in prompt_ok


def test_tone_only_accepts_known_template():
    """トーン変換は定型文IDでしか指定できない（自由文を渡せない）。"""
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        build_prompt(GenerateRequest(purpose="tone", level=1, template_id="unknown", tone="warm"))


def test_health():
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
