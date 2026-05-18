"""
ニュースフェッチャー: HackerNews API + RSS + yfinance
LLMへのコンテキスト注入用テキストを生成する
"""
import asyncio
import logging
import aiohttp
import feedparser
import yfinance as yf

log = logging.getLogger("news_fetcher")

HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"

RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
]

STOCK_TICKERS = ["^GSPC", "^N225", "BTC-USD"]


async def fetch_hackernews(n: int = 5) -> list[str]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(HN_TOP_URL) as resp:
                ids = (await resp.json())[:n]
            titles = []
            for item_id in ids:
                async with session.get(HN_ITEM_URL.format(item_id)) as r:
                    data = await r.json()
                    if data and data.get("title"):
                        titles.append(data["title"])
        return titles
    except Exception as e:
        log.warning(f"HackerNews取得失敗: {e}")
        return []


async def fetch_rss(max_items: int = 3) -> list[str]:
    items = []
    for url in RSS_FEEDS:
        try:
            feed = await asyncio.to_thread(feedparser.parse, url)
            for entry in feed.entries[:max_items]:
                items.append(entry.get("title", ""))
        except Exception as e:
            log.warning(f"RSS取得失敗 {url}: {e}")
    return [t for t in items if t]


async def fetch_stocks() -> str:
    lines = []
    for ticker in STOCK_TICKERS:
        try:
            info = await asyncio.to_thread(lambda t=ticker: yf.Ticker(t).fast_info)
            price = info.last_price
            lines.append(f"{ticker}: {price:,.2f}")
        except Exception as e:
            log.warning(f"株価取得失敗 {ticker}: {e}")
    return "\n".join(lines)


async def build_context() -> str:
    """ニュース・株価を並行取得してコンテキスト文字列を返す。"""
    from config import NIM_CONTEXT_MAX_CHARS
    hn, rss, stocks = await asyncio.gather(
        fetch_hackernews(3),   # 5→3 でトークン節約
        fetch_rss(2),
        fetch_stocks(),
    )
    parts = []
    if hn:
        parts.append("HN:" + " / ".join(hn))
    if rss:
        parts.append("News:" + " / ".join(rss[:4]))
    if stocks:
        parts.append(stocks)
    full = " | ".join(parts)
    # 文字数上限でinput tokens節約
    return full[:NIM_CONTEXT_MAX_CHARS]
