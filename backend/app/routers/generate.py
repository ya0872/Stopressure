"""Gemini を使う生成API。

設計上の制約:
  このエンドポイントは自由文を受け取らない。プロンプトはサーバ側でのみ組み立てる。
  purpose と level、定型文IDだけを受け取るため、ユーザーの入力文がここを通ることはない。

  夜の吐き出しは自由文を扱うため、専用の /reflection に分離してある。
  「ユーザーの言葉が外部へ出る経路」を1箇所に閉じ込め、監査対象を絞るための構成。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import settings_store as store
from ..services import gemini

router = APIRouter(prefix="/generate", tags=["generate"])

# このエンドポイントで扱う用途
ALLOWED_PURPOSES = {"meal", "reward", "tone"}

# 専用エンドポイントを持つ用途。ここでは受け付けず、正しい入口へ誘導する
DEDICATED_ENDPOINTS = {"reflection": "/api/v1/reflection"}

# トーン変換の対象にできる定型文。クライアントはIDでしか指定できない
TONE_TEMPLATES: dict[str, str] = {
    "affirm_default": "無事に一日を終えられただけで満点です。",
    "affirm_weather": "今日は気圧のせいです。あなたの側に落ち度はありません。",
    "affirm_rest": "できなかったのではなく、体が休むことを選んだ日です。",
}

TONES: dict[str, str] = {
    "plain": "淡々と、事実を述べるように",
    "warm": "親身に、寄り添うように",
    "casual": "砕けた口調で、友人が話すように",
}

# 省エネレベルごとの調理負荷の上限（docs/design.md §4.4）
MEAL_CONSTRAINT: dict[int, str] = {
    1: "作る前提でよい。ただし1品で完結すること",
    2: "作る前提でよい。ただし1品で完結すること",
    3: "火を使わない、または温めるだけで済むこと",
    4: "調理させないこと。買ってくる・頼むという選択肢にすること",
    5: "食べないという選択も肯定すること。無理に食べさせないこと",
}


class GenerateRequest(BaseModel):
    """自由文フィールドを意図的に持たない。

    text や prompt を受け取らないことが、この設計の要点である。
    """
    purpose: str = Field(description="meal | reward | tone")
    level: int = Field(ge=1, le=5, description="省エネレベル")
    template_id: str | None = Field(default=None, description="purpose=tone のときの定型文ID")
    tone: str | None = Field(default=None, description="purpose=tone のときの語り口")


class GenerateResponse(BaseModel):
    text: str
    model: str
    purpose: str


def build_prompt(req: GenerateRequest) -> tuple[str, str]:
    """(system, prompt) を組み立てる。入力はレベルとIDのみで、自由文は混入しない。"""
    if req.purpose == "meal":
        system = (
            "あなたは、疲れている人の食事を提案する係です。"
            "栄養指導はしません。判断の負担を減らすことだけが目的です。"
            "提案は必ず1案だけ。選択肢を並べないでください。40文字以内。"
        )
        prompt = (
            f"省エネレベルは{req.level}（1が平常、5が完全休止）です。"
            f"条件: {MEAL_CONSTRAINT[req.level]}。"
            "今日の食事を1案だけ提案してください。"
        )
        return system, prompt

    if req.purpose == "reward":
        system = (
            "あなたは、頑張らなかった人にご褒美を提案する係です。"
            "条件や引き換えを付けてはいけません。無条件に与えてください。30文字以内。"
        )
        # 運動を伴うご褒美はレベル1〜2に限る（docs/design.md §1.3）。
        # レベル3以上では「外出」も負荷になるため明示的に禁じる
        # （制約が「体を動かさない」だけだと、店に行く前提の案が返ってきたため）
        if req.level <= 2:
            allow_active = "運動や外出を伴うものも可"
        else:
            allow_active = "体を動かす必要がなく、家から出ずに済むものに限る"
        prompt = f"省エネレベルは{req.level}です。{allow_active}。ご褒美を1つ提案してください。"
        return system, prompt

    if req.purpose == "tone":
        template = TONE_TEMPLATES.get(req.template_id or "")
        tone_desc = TONES.get(req.tone or "")
        if not template or not tone_desc:
            raise HTTPException(status_code=400, detail="template_id と tone を正しく指定してください")
        system = (
            "あなたは文章の語り口だけを変える係です。"
            "意味を変えず、助言や励ましを足さないでください。"
        )
        prompt = f"次の文を「{tone_desc}」言い換えてください。1文で。\n\n{template}"
        return system, prompt

    raise HTTPException(status_code=400, detail=f"未知の purpose です: {req.purpose}")


@router.post("", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    """Geminiでテキストを生成する。"""
    if req.purpose in DEDICATED_ENDPOINTS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{req.purpose}' は専用エンドポイント {DEDICATED_ENDPOINTS[req.purpose]} を使ってください。"
                "このエンドポイントは自由文を受け取りません"
            ),
        )
    if req.purpose not in ALLOWED_PURPOSES:
        raise HTTPException(status_code=400, detail=f"未知の purpose です: {req.purpose}")

    key = store.resolve_gemini_api_key()
    if not key:
        raise HTTPException(status_code=409, detail="Gemini APIキーが未設定です。設定画面から登録してください")

    system, prompt = build_prompt(req)
    try:
        res = gemini.generate(key, store.resolve_gemini_model(), prompt, system=system)
    except gemini.GeminiSDKMissing as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except gemini.GeminiCallFailed as e:
        raise HTTPException(status_code=502, detail=f"生成に失敗しました: {e}") from e

    return GenerateResponse(text=res.text, model=res.model, purpose=req.purpose)
