"""
LLMサービス: NVIDIA NIM (meta/llama-3.3-70b-instruct) + キャラクター対話生成

NIM無料枠対策:
- 日次リクエストカウンター (NIM_MAX_DAILY_REQUESTS)
- generate_bgm_query() を廃止 → 事前定義リストで代替
- max_tokens削減・システムプロンプト圧縮
"""
from __future__ import annotations
import logging
import random
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
    return {
        "used": _counter_count,
        "limit": NIM_MAX_DAILY_REQUESTS,
        "remaining": NIM_MAX_DAILY_REQUESTS - _counter_count,
        "date": str(_counter_date),
    }


# ─── BGMクエリプール（LLM不使用）──────────────────────────
# "official audio" を付けることでカラオケ・cover版が上位に来にくくする
_BGM_POOL = [
    "lofi hip hop radio beats to relax study to official",
    "lofi jazz cafe background music official audio",
    "chill lofi beats no copyright free music",
    "smooth jazz background music official audio",
    "bossa nova cafe jazz official audio",
    "jazz coffee shop background music official",
    "ambient electronic chill background music official",
    "synthwave lo-fi no copyright official audio",
    "chillwave background music official audio",
    "classical piano background music official",
    "upbeat background music no copyright official",
    "funky jazz instrumental official audio",
    "piano lofi beats relaxing official",
    "acoustic guitar background chill official audio",
    "city pop japanese style official audio",
    "j-pop official audio BGM",
    "vaporwave aesthetic music official audio",
    "study music concentration official audio",
    "neo soul background music official",
    "indie pop chill music official audio",
]
_bgm_pool_index = 0

def pick_bgm_query() -> str:
    global _bgm_pool_index
    q = _BGM_POOL[_bgm_pool_index % len(_BGM_POOL)]
    _bgm_pool_index += 1
    return q


# ─── トピックプール（多様なジャンル）──────────────────────
_TOPIC_POOL = [
    # テクノロジー
    "最新AIと機械学習トレンド",
    "スマートフォン・ガジェットの最新情報",
    "ゲーム業界の最新ニュース",
    "宇宙開発とロケット技術の話",
    "サイバーセキュリティの最新動向",
    "電気自動車と自動運転技術",
    "メタバース・VR/ARの現在と未来",
    # サイエンス
    "宇宙と天文学の不思議な話",
    "最新の科学的発見や研究",
    "生物・動物の驚きの生態",
    "量子コンピュータって何がすごいの？",
    "地球環境と気候変動の最前線",
    # エンタメ・カルチャー
    "最近話題のアニメ・漫画",
    "音楽トレンドとおすすめアーティスト",
    "映画・ドラマのおすすめ・感想",
    "日本のポップカルチャーが世界に与える影響",
    "eスポーツの盛り上がりと大会情報",
    # 生活・食
    "日本のB級グルメと世界のおもしろ料理",
    "旅行・観光のおすすめスポット",
    "健康的な生活習慣とフィットネストレンド",
    "コーヒー・お茶・飲み物のこだわり話",
    # 社会・経済
    "仮想通貨・ブロックチェーンの現状",
    "働き方改革・リモートワークの変化",
    "若者のライフスタイルと消費トレンド",
    "サブスクサービスが変えた生活",
    # 面白・雑学
    "人類の歴史で最もインパクトがあった発明",
    "10年後の未来はどうなっている？",
    "もし〇〇が存在しなかったら…という妄想話",
    "世界の奇妙な法律・文化の違い",
    "睡眠と夢の科学",
    "言語と方言の面白い話",
    # スポーツ
    "サッカー・野球・バスケの最新情報",
    "日本のスポーツ界のホットな話題",
]

def pick_random_topic() -> str:
    """毎回異なるジャンルからランダムにトピックを選ぶ"""
    return random.choice(_TOPIC_POOL)


# ─── システムプロンプト ────────────────────────────────────
_SOLO_SYSTEM = (
    "あなたはAIポッドキャストDJ。明るく自然な日本語で3〜5文のトークを生成。"
    "話を膨らませてリスナーが楽しめる内容にする。捏造は禁止。"
)


def _build_dialogue_system(chars: list, has_context: bool) -> str:
    char_desc = " / ".join(f"{c.name}({c.role}:{c.style})" for c in chars)
    n      = len(chars)
    turns  = n * 3          # 2人→6ターン、3人→9ターン
    max_t  = n * 4          # 2人→最大8ターン
    first  = chars[0].name
    last   = chars[-1].name
    ctx_rule = "提供情報を活かしつつ自分の意見も入れる。" if has_context else "自由に会話してよい。捏造禁止。"

    return (
        f"AIポッドキャスト台本ライター。登場:{char_desc}\n"
        f"ルール:「名前: セリフ」形式のみ出力。{turns}〜{max_t}行。"
        f"1セリフ60字以内。最初は{first}から始める。各キャラのstyleを厳守。"
        f"{ctx_rule}"
        f"自然な会話の流れを作り、最後は{first}か{last}が締める。"
    )


# ─── 生成関数 ─────────────────────────────────────────────

async def generate_talk(topic: str, context: str = "") -> str:
    """ソロトーク生成"""
    if not _can_request():
        return ""
    user_content = f"トピック: {topic}" if topic else f"トピック: {pick_random_topic()}"
    if context:
        user_content += f"\n【参考情報】{context}"

    _inc_counter()
    resp = await _client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": _SOLO_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
        max_tokens=200,
        temperature=0.8,
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

    # トピック未指定→ランダム選択（AIニュース固定を解消）
    resolved_topic = topic.strip() or pick_random_topic()
    user_content = f"テーマ: {resolved_topic}"
    if context:
        user_content += f"\n【参考情報】{context}"

    log.info(f"対話生成: topic={resolved_topic!r} cast={[c.name for c in chars]}")
    _inc_counter()
    resp = await _client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": _build_dialogue_system(chars, bool(context))},
            {"role": "user",   "content": user_content},
        ],
        max_tokens=600,
        temperature=0.85,
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

