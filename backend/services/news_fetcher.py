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
    hn, rss, stocks = await asyncio.gather(
        fetch_hackernews(5),
        fetch_rss(3),
        fetch_stocks(),
    )
    parts = []
    if hn:
        parts.append("【Hacker News トレンド】\n" + "\n".join(f"- {t}" for t in hn))
    if rss:
        parts.append("【海外ニュース】\n" + "\n".join(f"- {t}" for t in rss))
    if stocks:
        parts.append("【市場情報】\n" + stocks)
    return "\n\n".join(parts)
