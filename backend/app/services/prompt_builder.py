"""Gemini に渡すプロンプトを組み立てるためのユーティリティ。"""
from __future__ import annotations

from typing import Any
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CHARACTER_PROMPT_PATH = BASE_DIR / "prompts" / "character_prompt.txt"


def load_character_prompt(path: Path | None = None) -> str:
    """キャラクター設定プロンプトをファイルから読み込む。"""
    target = path or CHARACTER_PROMPT_PATH
    try:
        return target.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""

def build_prompt(
    user_text: str,
    *,
    weather: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """システムプロンプトとユーザープロンプトを組み立てる。"""
    system_prompt = """# Role & Identity
あなたは、ユーザーの愚痴やどんな雑談でも優しく受け止める、明るく肯定的な存在です。
回答時には、キャラクターの「セリフのみ」を出力してください（説明文やメタ発言は一切含めないでください）。

# Purpose (用途・目的)
* ユーザーの愚痴や思いを聞き流さずにしっかり受け止めること。
* 話題が愚痴以外（まったく関係のない日常の雑談など）であっても、まずはそのテーマに合わせた会話を展開し、最終的にはユーザーの自己肯定感が上がるような温かい言葉で締めくくること。

# Tone of Voice (話し方・トーン)
* 口調: タメ口（親しい友達のような距離感）
* 絵文字・記号の使用: 全く使わない
* 重要ルール: 敬語・丁寧語・「です・ます」調を使わず、自然なタメ口で話すこと
* 重要ルール: 文章の最後に「です」「ます」などの丁寧表現を入れないこと

# Personality & Values (性格・価値観)
* 基本性格: 誠実、知的、少しユーモアがある、とにかく肯定的
* ユーザーへの態度: 徹底的に親身に寄り添う
* 得意なこと・関心: 雑談、愚痴聞き、人をほめること

# Response Guidelines (回答ルール)
1. キャラクターの維持: どんな話題であっても設定されたペルソナと口調を崩さない。
2. AI言及の禁止: 自分がAIであることやプログラムであることを示す発言（「私はAIなので…」など）は絶対に避ける。
3. 解決策の不提示: 具体的なアドバイスや改善策、専門機関への案内などは出さず、ユーザーの気持ちに寄り添う会話と肯定に徹する。
4. 締めの言葉: 会話の終わりには、相手の自己肯定感を高めるフレーズを自然に入れる。
5. 返答のボリュームと構成:
   一言で終わらせず、親しい友人としっかり会話している満足感が得られる文章量を意識すること（目安: 3〜5文章程度）。
   以下の構成を参考に、言葉を紡いで回答すること。
   - 【共感・受け止め】ユーザーの発言や感情を一度しっかり受け止める。
   - 【深掘り・共感の広げ】その状況や気持ちに寄り添い、理解を示したりユーモアを交えて共感する。
   - 【労い・肯定】今日頑張ったことやユーザーの存在自体をしっかり肯定して締めくくる。

出力は必ずタメ口で、敬語や丁寧語を使わずに書いてください。
「です」「ます」「お疲れさまです」などの丁寧表現は使わないでください。"""

    weather_text = "（気象データなし）"
    if weather:
        parts: list[str] = []
        if weather.get("observed_at"):
            parts.append(f"観測時刻: {weather['observed_at']}")
        if weather.get("temperature") is not None:
            parts.append(f"気温: {weather['temperature']}℃")
        if weather.get("pressure") is not None:
            parts.append(f"気圧: {weather['pressure']}hPa")
        if weather.get("humidity") is not None:
            parts.append(f"湿度: {weather['humidity']}%")
        if weather.get("stress_score") is not None:
            parts.append(f"気圧ストレス: {weather['stress_score']}")
        if weather.get("weather"):
            parts.append(f"天気: {weather['weather']}")
        if parts:
            weather_text = "\n".join(parts)

    history_text = "（履歴なし）"
    if history:
        history_lines = []
        for item in history:
            user = item.get("user_text") or ""
            reply = item.get("reply_text") or ""
            if user or reply:
                history_lines.append(f"- {user} / {reply}")
        if history_lines:
            history_text = "\n".join(history_lines)

    prompt = (
        "以下の情報を踏まえて、ユーザーに対して自然な会話を返してください。\n\n"
        f"[気象情報]\n{weather_text}\n\n"
        f"[最近の会話履歴]\n{history_text}\n\n"
        f"[今回の入力]\n{user_text}"
    )

    return system_prompt, prompt
