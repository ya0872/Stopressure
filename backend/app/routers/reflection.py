"""夜の吐き出しへの応答を生成する。

このエンドポイントだけが自由文を受け取る。/generate 側に自由文フィールドを足さず
専用の入口を分けているのは、「どこからユーザーの言葉が外部へ出るのか」を1箇所に
閉じ込めるため。監査するときはこのファイルだけを見ればよい。

送信先について:
  版0.2では「ローカルLLM固定」としていたが、利用者の判断により Gemini を使う構成に変更した
  （docs/design.md §3.3）。入力内容は Google に送信される。画面側でその旨を明示すること。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import settings_store as store
from ..db import get_conn
from ..services import gemini, usage_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reflection", tags=["reflection"])

# 設計書 §4.7 の制約をそのままシステムプロンプトにする
SYSTEM_PROMPT = """あなたはユーザーを全面的に肯定する聞き役です。以下を厳守してください。
- 助言、提案、励まし（「明日は頑張って」等）を一切含めない
- 原因をユーザーの努力不足に帰属させない
- 気象条件を根拠に「仕方がなかった」と外部帰属させる
- 2〜3文、100文字以内で応答する
- 「無事に過ごせただけで満点」という趣旨を必ず含める
- 質問を返さない。会話を続けようとしない"""

# 生成に失敗したときに返す文。UIを空にしないための最低保証
FALLBACK_REPLIES = [
    "無事に一日を終えられただけで満点です。気圧がこれだけ動いた日に、それ以上は誰にもできません。",
    "できなかったのではなく、体が休むことを選んだ日です。今日を越えられたことが、そのまま成果です。",
]

# そのフェーズの上限に達したときに返す文（依存防止 / §4.8）。
# 上の SYSTEM_PROMPT と同じ制約（助言を含めない・100文字以内・「満点」の趣旨を含む）を
# 満たすように書いてある。「制限」という語は使わない
LIMIT_REACHED_REPLY = "受け取りました。今日はもう十分に言葉にできています。無事に過ごせただけで満点です。"


class ReflectionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000, description="吐き出した内容")
    level: int | None = Field(default=None, ge=1, le=5, description="その日の省エネレベル")
    felt: int | None = Field(default=None, ge=1, le=3, description="体感 1:つらい 2:普通 3:平気")


class ReflectionResponse(BaseModel):
    """応答本体。

    reason について: これは**開発者向けの切り分け情報であって、画面に出すものではない**。
    上限到達と生成失敗はどちらも 200 + fallback=true + model=null で返るため、これが無いと
    「Geminiが壊れた」のか「今日はもう3回話した」のかを区別できず、実際に切り分けに失敗した
    （docs/gemini-fallback-fixes-2026-08-02.txt）。
    回数は載せない。「あと何回」を見せないという §1.2 / §4.8 の制約はそのまま守る。
    """
    reply: str
    model: str | None = Field(default=None, description="生成に使ったモデル。定型文の場合は null")
    fallback: bool = Field(description="Geminiを通さずに定型文を返したか")
    reason: str | None = Field(
        default=None,
        description="fallback の理由: limit（上限到達） | error（生成失敗）。生成できたなら null",
    )


def _build_prompt(req: ReflectionRequest) -> str:
    level_note = (
        f"今日の省エネレベルは{req.level}（1が平常、5が完全休止）でした。"
        if req.level
        else ""
    )
    return f"{level_note}次の言葉を受け止めてください。\n\n{req.text}"


def _save(req: ReflectionRequest, reply: str) -> None:
    now = datetime.now(timezone.utc)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO reflection (date, user_text, reply_text, level, felt, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (now.date().isoformat(), req.text, reply, req.level, req.felt, now.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


@router.post("", response_model=ReflectionResponse)
def create_reflection(req: ReflectionRequest) -> ReflectionResponse:
    """吐き出しを受け取り、全肯定の応答を返す。"""
    key = store.resolve_gemini_api_key()
    if not key:
        raise HTTPException(
            status_code=409,
            detail="Gemini APIキーが未設定です。設定画面から登録してください",
        )

    # 依存防止（docs/design.md §4.8）。上限に達していたらGeminiを呼ばない。
    # ただし /generate と違い 429 では突き返さない。吐き出しは受け取って記録し、
    # 定型の肯定を返す。門前払いすると、このファイルが避けようとしている
    # 「吐き出したのに無視された」体験そのものになるため
    if usage_limit.peek("reflection").blocked:
        _save(req, LIMIT_REACHED_REPLY)
        return ReflectionResponse(
            reply=LIMIT_REACHED_REPLY, model=None, fallback=True, reason="limit"
        )

    current_model = store.resolve_gemini_model()
    reason: str | None = None
    try:
        res = gemini.generate(key, current_model, _build_prompt(req), system=SYSTEM_PROMPT)
        reply, model, fallback = res.text, res.model, False
    except (gemini.GeminiCallFailed, gemini.GeminiSDKMissing):
        # 通信断や安全フィルタで落ちても、ユーザーには必ず肯定を返す。
        # ここで500を返すと「吐き出したのに無視された」体験になるため握る。
        #
        # ただし握るのは利用者への見せ方だけで、理由は必ずログへ出す。以前はここが無言で、
        # 画面には定型文、レスポンスは 200 + model: null しか残らなかったため、
        # 「モデル名が使えない」のか「通信が切れた」のかをDBを見るまで区別できなかった。
        # 使えないモデルを設定したときは、ここに 400/429 の本文がそのまま出る
        logger.warning(
            "Gemini生成に失敗したため定型文を返します (model=%s)", current_model, exc_info=True
        )
        reply, model, fallback, reason = FALLBACK_REPLIES[0], None, True, "error"

    # 生成が成立した回だけ数える。定型文で返した回は枠を消費させない
    if not fallback:
        usage_limit.record("reflection")

    _save(req, reply)
    return ReflectionResponse(reply=reply, model=model, fallback=fallback, reason=reason)
