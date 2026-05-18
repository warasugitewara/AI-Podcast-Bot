"""
LLMサービス: OpenAI互換API + コンテキスト注入
"""
import logging
from openai import AsyncOpenAI
from config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL

log = logging.getLogger("llm")

_client = AsyncOpenAI(base_url=LLM_API_BASE, api_key=LLM_API_KEY)

RADIO_SYSTEM_PROMPT = """あなたはAI Podcast BotのDJです。
明るく自然な日本語で、2〜4文程度のトークを生成してください。
提供されたコンテキスト情報（ニュース・株価など）を必ず参考にし、
独自に事実を作り出すことは絶対に禁止です。"""


async def generate_talk(
    topic: str,
    context: str = "",
    system_prompt: str = RADIO_SYSTEM_PROMPT,
    model: str = LLM_MODEL,
) -> str:
    """ラジオトーク生成。contextにニュース等を注入してハルシネーションを抑制。"""
    user_content = f"トピック: {topic}"
    if context:
        user_content += f"\n\n【参考情報】\n{context}"

    log.info(f"LLM生成開始: topic={topic!r}")
    resp = await _client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ],
        max_tokens=300,
        temperature=0.7,
    )
    text = resp.choices[0].message.content.strip()
    log.info(f"LLM生成完了: {len(text)}文字")
    return text


async def generate_bgm_query(context: str = "") -> str:
    """時間帯・トピックに合わせたBGM検索クエリをLLMに生成させる。"""
    prompt = "現在のラジオの雰囲気に合うBGMのYouTube検索キーワードを1つだけ英語で答えてください。"
    if context:
        prompt += f"\n【状況】{context}"

    resp = await _client.chat.completions.create(
        model=model if (model := LLM_MODEL) else "gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=30,
        temperature=0.8,
    )
    return resp.choices[0].message.content.strip().strip('"')
