"""
YouTube Music サービス: トレンド曲取得 (ytmusicapi)
- JP/グローバルチャートをキャッシュ付きで取得
- 認証不要（公開データのみ）
"""
from __future__ import annotations
import asyncio
import logging
import random
import time

log = logging.getLogger("ytmusic")

_CACHE_TTL = 6 * 3600  # 6時間

_cache: dict[str, tuple[list[dict], float]] = {}  # country → (songs, timestamp)


def _fetch_trending(country: str, limit: int) -> list[dict]:
    from ytmusicapi import YTMusic
    yt     = YTMusic()
    charts = yt.get_charts(country=country)
    videos = charts.get("videos", [])
    if not videos:
        return []

    playlist_id = videos[0].get("playlistId") if isinstance(videos[0], dict) else None
    if not playlist_id:
        return []

    pl     = yt.get_playlist(playlist_id, limit=limit)
    tracks = []
    for t in pl.get("tracks", []):
        vid = t.get("videoId")
        if not vid:
            continue
        artist = ""
        if t.get("artists"):
            artist = t["artists"][0].get("name", "")
        tracks.append({
            "title":    t.get("title", ""),
            "artist":   artist,
            "video_id": vid,
            "url":      f"https://music.youtube.com/watch?v={vid}",
        })
    return tracks


async def get_trending_songs(country: str = "JP", limit: int = 20) -> list[dict]:
    """YouTube Music トレンド曲リストを返す（6時間キャッシュ）"""
    cached_songs, cached_at = _cache.get(country, ([], 0.0))
    if cached_songs and time.monotonic() - cached_at < _CACHE_TTL:
        return cached_songs[:limit]

    try:
        songs = await asyncio.to_thread(_fetch_trending, country, limit)
        if songs:
            _cache[country] = (songs, time.monotonic())
            log.info(f"YouTube Musicトレンド更新: {len(songs)}曲 ({country})")
        return songs
    except Exception as e:
        log.warning(f"YouTube Musicトレンド取得失敗 ({country}): {e}")
        return cached_songs[:limit]  # キャッシュが残っていれば返す


async def pick_trending_url(country: str = "JP") -> str | None:
    """トレンド曲からランダムに1曲のURLを返す"""
    songs = await get_trending_songs(country=country)
    if not songs:
        return None
    song = random.choice(songs)
    log.info(f"トレンド選曲: {song['title']} / {song['artist']}")
    return song["url"]
