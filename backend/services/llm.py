"""
LLMサービス: NVIDIA NIM (meta/llama-3.3-70b-instruct) + キャラクター対話生成

NIM無料枠対策:
- 日次リクエストカウンター (NIM_MAX_DAILY_REQUESTS)
- generate_bgm_query() を廃止 → 事前定義リストで代替
- max_tokens削減・システムプロンプト圧縮
"""
from __future__ import annotations
import logging
import time
from datetime import date
from openai import AsyncOpenAI
from config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL, NIM_MAX_DAILY_REQUESTS

log = logging.getLogger("llm")

_client = AsyncOpenAI(base_url=LLM_API_BASE, api_key=LLM_API_KEY)

# ─── 日次リクエストカウンター ──────────────────────────────
_counter_date: date = date.today()
_counter_count: int = 0

def _can_request() -> bool:
    """日次上限チェック。超えていたら False を返す。"""
    global _counter_date, _counter_count
    today = date.today()
    if today != _counter_date:
        _counter_date  = today
        _counter_count = 0
    if _counter_count >= NIM_MAX_DAILY_REQUESTS:
        log.warning(f"NIM日次上限到達 ({NIM_MAX_DAILY_REQUESTS}件/日)。生成をスキップします。")
        return False
    return True

def _inc_counter():
    global _counter_count
    _counter_count += 1
    remaining = NIM_MAX_DAILY_REQUESTS - _counter_count
    log.info(f"NIM使用: {_counter_count}/{NIM_MAX_DAILY_REQUESTS} (残{remaining}件)")

def get_daily_usage() -> dict:
    return {"used": _counter_count, "limit": NIM_MAX_DAILY_REQUESTS, "date": str(_counter_date)}


# ─── BGMクエリ（事前定義リスト - LLM不使用）─────────────────
# generate_bgm_query() を廃止しAPIコールを節約
_BGM_POOL = [
    "lofi hip hop radio beats to relax study to",
    "lofi jazz cafe background music",
    "chill lofi beats no copyright free",
    "smooth jazz background music instrumental",
    "bossa nova cafe jazz music",
    "jazz coffee shop background music",
    "ambient electronic chill background music",
    "synthwave lo-fi no copyright",
    "chillwave background music instrumental",
    "light classical background music piano",
    "upbeat background music no copyright instrumental",
    "funky jazz background instrumental",
    "piano lofi beats relaxing",
    "guitar acoustic background chill",
    "city pop japanese style instrumental",
]
_bgm_pool_index = 0

def pick_bgm_query() -> str:
    """事前定義リストからラウンドロビンでBGMクエリを返す。APIコール不要。"""
    global _bgm_pool_index
    q = _BGM_POOL[_bgm_pool_index % len(_BGM_POOL)]
    _bgm_pool_index += 1
    return q


# ─── システムプロンプト ────────────────────────────────────
_SOLO_SYSTEM = "あなたはAIポッドキャストDJ。明るい日本語で2〜3文のトークを生成。提供情報のみ使用、捏造禁止。"


def _build_dialogue_system(chars: list) -> str:
    """キャラクターリストからシステムプロンプトを組み立てる（トークン節約版）"""
    char_desc = " / ".join(f"{c.name}({c.role}:{c.style})" for c in chars)
    n      = len(chars)
    turns  = n * 2
    first  = chars[0].name
    last   = chars[-1].name

    return (
        f"AIポッドキャスト台本ライター。登場:{char_desc}\n"
        f"ルール:「名前: セリフ」形式のみ出力。{turns}〜{turns+n}行。"
        f"1セリフ40字以内。最初は{first}から。各キャラのstyleを厳守。"
        f"提供情報のみ使用・捏造禁止。最後は{first}か{last}がまとめる。"
    )


# ─── 生成関数 ─────────────────────────────────────────────

async def generate_talk(topic: str, context: str = "") -> str:
    """ソロトーク生成"""
    if not _can_request():
        return ""
    user_content = f"トピック: {topic}" if topic else "今日の技術トレンド"
    if context:
        user_content += f"\n【情報】{context}"

    _inc_counter()
    resp = await _client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": _SOLO_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
        max_tokens=150,
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


async def generate_dialogue(
    topic: str,
    context: str = "",
    chars: list | None = None,
) -> list[dict]:
    """
    キャラクター対話台本を生成。
    戻り値: [{"speaker": "ハル", "text": "..."}, ...]
    日次上限超過時は空リストを返す（呼び出し側でBGMにフォールバック）。
    """
    if not _can_request():
        return []

    from services.character_manager import character_manager
    if chars is None:
        chars = character_manager.active()

    user_content = f"テーマ: {topic}" if topic else "最新AI・テクノロジーニュース"
    if context:
        user_content += f"\n【情報】{context}"

    log.info(f"対話生成: topic={topic!r} cast={[c.name for c in chars]}")
    _inc_counter()
    resp = await _client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": _build_dialogue_system(chars)},
            {"role": "user",   "content": user_content},
        ],
        max_tokens=350,
        temperature=0.8,
    )
    raw = resp.choices[0].message.content.strip()
    log.info(f"対話生成完了: {len(raw)}文字")

    valid_names = {c.name for c in chars}
    lines = _parse_dialogue(raw, valid_names)
    if not lines:
        log.warning(f"パース失敗。raw:\n{raw[:300]}")
    return lines


def _parse_dialogue(raw: str, valid_names: set[str]) -> list[dict]:
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        for name in valid_names:
            for sep in (": ", "： ", ":"):
                if line.startswith(name + sep):
                    text = line[len(name + sep):].strip()
                    if text:
                        lines.append({"speaker": name, "text": text})
                    break
    return lines

