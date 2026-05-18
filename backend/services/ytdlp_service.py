"""
yt-dlpサービス: BGMのYouTube/YouTube Music 検索・ダウンロード・キャッシュ管理
YouTube URL / YouTube Music URL の直接ダウンロードにも対応。
カラオケ・オフボーカル・cover版を自動排除して正規音源のみ取得。
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
    "ratelimit": 500_000,
    "cachedir": str(BGM_CACHE_DIR / ".ydl_cache"),
    "noplaylist": True,
}

# ─── カラオケ/粗悪コンテンツのフィルター ──────────────────────
# タイトルにこれらが含まれる動画を弾く
_REJECT_RE = re.compile(
    r"カラオケ|karaoke|off\s*vocal|オフボーカル|歌ってみた|cover|covered by|"
    r"instrumental\s*version|\(inst[.\s)]|\[inst[.\s)]|piano ver|acoustic ver|"
    r"remake|リメイク|弾いてみた|叩いてみた|tribute|reaction|lyrics?\s*video",
    re.IGNORECASE,
)

# チャンネル名に含まれる怪しいキーワード（カラオケ専門チャンネル等）
_REJECT_CHANNEL_RE = re.compile(
    r"karaoke|カラオケ|off\s*vocal|歌ってみた|instrumental",
    re.IGNORECASE,
)


def _is_bad_entry(info: dict) -> bool:
    """カラオケ・cover等の不適切な動画かどうか判定する"""
    title   = info.get("title", "")
    channel = info.get("channel", "") or info.get("uploader", "")
    if _REJECT_RE.search(title):
        log.debug(f"タイトル除外: {title!r}")
        return True
    if _REJECT_CHANNEL_RE.search(channel):
        log.debug(f"チャンネル除外: {channel!r} ({title!r})")
        return True
    return False


_YT_URL_RE = re.compile(
    r"https?://(www\.)?(youtube\.com/watch|youtu\.be/|"
    r"music\.youtube\.com/watch|youtube\.com/playlist|music\.youtube\.com/playlist)",
    re.IGNORECASE,
)


def is_youtube_url(s: str) -> bool:
    return bool(_YT_URL_RE.match(s.strip()))


def _cache_path_for_id(video_id: str) -> Path | None:
    for ext in ("opus", "webm", "m4a", "mp3"):
        p = BGM_CACHE_DIR / f"{video_id}.{ext}"
        if p.exists():
            return p
    return None


async def download_url(url: str, max_duration: int = 600) -> tuple[Path | None, str]:
    """YouTube / YouTube Music の URL を直接ダウンロード。(path, title) を返す。"""
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
            return None, ""
        # URL直指定はユーザーが選んだものなのでカラオケでも許容するが警告は出す
        if _is_bad_entry(info):
            log.warning(f"URL指定の動画がカラオケ系の可能性: {info.get('title')!r}")
        cached = _cache_path_for_id(info["id"])
        title  = info.get("title", "")
        if cached:
            log.info(f"URLダウンロード完了: {title!r} → {cached.name}")
            return cached, title
    except Exception as e:
        log.error(f"URLダウンロード失敗 ({url}): {e}")
    return None, ""


async def search_and_download(query: str, max_duration: int = 600) -> tuple[Path | None, str]:
    """
    クエリでYouTube検索し、カラオケ等を除外した最初の曲をDLして (path, title) を返す。
    最大 SEARCH_CANDIDATES 件を取得してフィルタリング。
    """
    SEARCH_CANDIDATES = 8
    # メタデータだけ先に取得し、良い候補を選んでからダウンロード
    meta_opts = {
        **YDL_OPTS_BASE,
        "extract_flat": "in_playlist",   # ダウンロードせず情報だけ取得
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
    }
    dl_opts = {
        **YDL_OPTS_BASE,
        "match_filter": yt_dlp.utils.match_filter_func(f"duration < {max_duration}"),
    }

    def _fetch_meta():
        with yt_dlp.YoutubeDL(meta_opts) as ydl:
            result = ydl.extract_info(
                f"ytsearch{SEARCH_CANDIDATES}:{query}",
                download=False,
            )
            return result.get("entries", []) if result else []

    def _download_one(video_url: str):
        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            return info

    try:
        entries = await asyncio.to_thread(_fetch_meta)
        if not entries:
            log.warning(f"検索結果なし: {query!r}")
            return None, ""

        # 候補をフィルタリングして最初の良いものを選ぶ
        chosen = None
        for entry in entries:
            if entry and not _is_bad_entry(entry):
                chosen = entry
                break

        if chosen is None:
            # 全部弾かれた場合は最初の候補を使う（最終手段）
            chosen = entries[0]
            log.warning(f"全候補がフィルター対象。最初の結果を使用: {chosen.get('title')!r}")

        video_url = chosen.get("url") or f"https://www.youtube.com/watch?v={chosen['id']}"
        log.info(f"BGM選択: {chosen.get('title')!r} (フィルター通過)")

        info = await asyncio.to_thread(_download_one, video_url)
        if not info:
            return None, ""

        cached = _cache_path_for_id(info["id"])
        title  = info.get("title", query)
        if cached:
            log.info(f"BGMダウンロード完了: {title!r} → {cached.name}")
            return cached, title

    except Exception as e:
        log.error(f"yt-dlp失敗 ({query}): {e}")
    return None, ""


async def get_bgm(query_or_url: str) -> tuple[Path | None, str]:
    """URLなら直接DL、キーワードなら検索DL。キャッシュ確認付き。(path, title) を返す。"""
    s = query_or_url.strip()

    if is_youtube_url(s):
        return await download_url(s)

    # キーワード検索: クエリのMD5でキャッシュ確認
    key = hashlib.md5(s.encode()).hexdigest()[:8]
    for p in BGM_CACHE_DIR.glob("*.opus"):
        if p.stem.startswith(key):
            log.debug(f"BGMキャッシュ使用: {p.name}")
            return p, s
    return await search_and_download(s)


