"""
BgmWorker: bgm_prefetch_queue からクエリを取り出し、
yt-dlp で音楽をダウンロード → playback_queue に投入する。
ダウンロード開始時に idle_event をクリアして再生中扱いにする。
"""
import asyncio
import logging

from services.ytdlp_service import get_bgm
from services.llm import pick_bgm_query

log = logging.getLogger("bgm_worker")


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

                query   = job.get("query") or pick_bgm_query()
                enqueue = job.get("enqueue", True)

                await self._push_status("bgm_fetching", query)
                log.info(f"BGM取得開始: {query!r}")

                bgm_path = await get_bgm(query)
                if bgm_path and enqueue:
                    await self.playback_queue.put({"type": "bgm", "wav_path": bgm_path})
                    log.info(f"BGM → playback_queue: {bgm_path.name}")
                    await self._push_status("bgm_ready", bgm_path.name)
                else:
                    log.warning(f"BGM取得失敗: {query!r}")
                    await self._push_status("bgm_failed", query)
                    # 失敗時はアイドルに戻す（PlaybackWorkerが設定しないため）
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
