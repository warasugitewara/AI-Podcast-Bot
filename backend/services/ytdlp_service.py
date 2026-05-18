"""
yt-dlpサービス: BGMのYouTube/YouTube Music 検索・ダウンロード・キャッシュ管理
YouTube URL / YouTube Music URL の直接ダウンロードにも対応。
"""
import asyncio
import hashlib
import logging
import re
from pathlib import Path
import yt_dlp

from config import BGM_CACHE_DIR

log = logging.getLogger("ytdlp")

BGM_CACHE_DIR.mkdir(parents=True, exist_ok=True)

YDL_OPTS_BASE = {
    "format": "bestaudio/best",
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "opus",
        "preferredquality": "128",
    }],
    "outtmpl": str(BGM_CACHE_DIR / "%(id)s.%(ext)s"),
    "quiet": True,
    "no_warnings": True,
    "ratelimit": 500_000,          # 500KB/s レート制限
    "cachedir": str(BGM_CACHE_DIR / ".ydl_cache"),
    "noplaylist": True,            # プレイリスト指定時も最初の1曲のみ
}

_YT_URL_RE = re.compile(
    r"https?://(www\.)?(youtube\.com/watch|youtu\.be/|"
    r"music\.youtube\.com/watch|youtube\.com/playlist|music\.youtube\.com/playlist)",
    re.IGNORECASE,
)


def is_youtube_url(s: str) -> bool:
    """YouTube / YouTube Music URLかどうか判定"""
    return bool(_YT_URL_RE.match(s.strip()))


def _cache_path_for_id(video_id: str) -> Path | None:
    for ext in ("opus", "webm", "m4a", "mp3"):
        p = BGM_CACHE_DIR / f"{video_id}.{ext}"
        if p.exists():
            return p
    return None


async def download_url(url: str, max_duration: int = 600) -> Path | None:
    """YouTube / YouTube Music の URL を直接ダウンロード"""
    opts = {
        **YDL_OPTS_BASE,
        "match_filter": yt_dlp.utils.match_filter_func(f"duration < {max_duration}"),
    }

    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info and "entries" in info:
                info = info["entries"][0]
            return info

    try:
        info = await asyncio.to_thread(_run)
        if not info:
            return None
        cached = _cache_path_for_id(info["id"])
        if cached:
            log.info(f"URLダウンロード完了: {info.get('title', '?')} → {cached.name}")
            return cached
    except Exception as e:
        log.error(f"URLダウンロード失敗 ({url}): {e}")
    return None


async def search_and_download(query: str, max_duration: int = 600) -> Path | None:
    """クエリでYouTube検索し、最初にヒットした曲をダウンロードしてPathを返す。"""
    search_url = f"ytsearch1:{query}"
    opts = {
        **YDL_OPTS_BASE,
        "match_filter": yt_dlp.utils.match_filter_func(f"duration < {max_duration}"),
    }

    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(search_url, download=True)
            if info and "entries" in info:
                info = info["entries"][0]
            return info

    try:
        info = await asyncio.to_thread(_run)
        if not info:
            return None
        cached = _cache_path_for_id(info["id"])
        if cached:
            log.info(f"BGMダウンロード完了: {info.get('title','?')} → {cached.name}")
            return cached
    except Exception as e:
        log.error(f"yt-dlp失敗 ({query}): {e}")
    return None


async def get_bgm(query_or_url: str) -> Path | None:
    """URLなら直接ダウンロード、キーワードなら検索ダウンロード。キャッシュ確認付き。"""
    s = query_or_url.strip()

    if is_youtube_url(s):
        return await download_url(s)

    # キーワード検索: クエリのMD5でキャッシュ確認
    key = hashlib.md5(s.encode()).hexdigest()[:8]
    for p in BGM_CACHE_DIR.glob("*.opus"):
        if p.stem.startswith(key):
            log.debug(f"BGMキャッシュ使用: {p.name}")
            return p
    return await search_and_download(s)

