"""
BgmWorker: bgm_prefetch_queue からクエリ/URLを取り出し、
yt-dlp で音楽をダウンロード → playback_queue に投入する。
- YouTube URL / YouTube Music URL の直接ダウンロードに対応
- クエリ未指定時: 30%の確率でYouTube Musicトレンド曲、残りはプリセット
"""
import asyncio
import logging
import random

from services.ytdlp_service import get_bgm
from services.llm import pick_bgm_query

log = logging.getLogger("bgm_worker")


async def _resolve_query(job: dict) -> str:
    """ジョブからBGMクエリ/URLを決定する"""
    q = job.get("query", "").strip()
    if q:
        return q  # ユーザー指定 (URL or キーワード) を最優先

    # 30%の確率でYouTube Musicトレンド曲を選択
    if random.random() < 0.3:
        try:
            from services.ytmusic_service import pick_trending_url
            url = await pick_trending_url(country="JP")
            if url:
                return url
        except Exception as e:
            log.debug(f"トレンド取得スキップ: {e}")

    return pick_bgm_query()  # プリセットリストから選択


class BgmWorker:
    def __init__(
        self,
        bgm_prefetch_q: asyncio.Queue,
        playback_queue: asyncio.Queue,
        status_queue:   asyncio.Queue,
        idle_event:     asyncio.Event,
    ):
        self.bgm_prefetch_q = bgm_prefetch_q
        self.playback_queue = playback_queue
        self.status_queue   = status_queue
        self.idle_event     = idle_event

    async def run(self):
        log.info("BgmWorker 起動")
        while True:
            try:
                job = await self.bgm_prefetch_q.get()

                # ダウンロード開始時点でビジーマーク（race condition防止）
                self.idle_event.clear()

                query   = await _resolve_query(job)
                enqueue = job.get("enqueue", True)

                await self._push_status("bgm_fetching", query[:60])
                log.info(f"BGM取得開始: {query!r}")

                bgm_path = await get_bgm(query)
                if bgm_path and enqueue:
                    await self.playback_queue.put({"type": "bgm", "wav_path": bgm_path})
                    log.info(f"BGM → playback_queue: {bgm_path.name}")
                    await self._push_status("bgm_ready", bgm_path.name)
                else:
                    log.warning(f"BGM取得失敗: {query!r}")
                    await self._push_status("bgm_failed", query[:60])
                    if self.playback_queue.empty():
                        self.idle_event.set()

                self.bgm_prefetch_q.task_done()

            except asyncio.CancelledError:
                log.info("BgmWorker 停止")
                break
            except Exception as e:
                log.error(f"BgmWorker エラー: {e}", exc_info=True)
                self.idle_event.set()
                await asyncio.sleep(5)

    async def _push_status(self, event: str, detail: str = ""):
        try:
            self.status_queue.put_nowait({"event": event, "detail": detail})
        except asyncio.QueueFull:
            pass

