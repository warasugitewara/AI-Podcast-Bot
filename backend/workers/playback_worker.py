"""
PlaybackWorker: playback_queue から音声ジョブを取り出し、
ffmpeg 経由で Discord VoiceClient に再生する。
再生完了まで待機し、次のジョブへ進む。
"""
import asyncio
import logging
from pathlib import Path

import discord

log = logging.getLogger("playback_worker")


class PlaybackWorker:
    def __init__(self, playback_queue: asyncio.Queue, bot, status_queue: asyncio.Queue):
        self.playback_queue = playback_queue
        self.bot            = bot
        self.status_queue   = status_queue
        self._done_event    = asyncio.Event()

    async def run(self):
        log.info("PlaybackWorker 起動")
        while True:
            try:
                job = await self.playback_queue.get()
                await self._play(job)
                self.playback_queue.task_done()

            except asyncio.CancelledError:
                log.info("PlaybackWorker 停止")
                break
            except Exception as e:
                log.error(f"PlaybackWorker エラー: {e}", exc_info=True)
                await asyncio.sleep(3)

    async def _play(self, job: dict):
        wav_path: Path = job["wav_path"]
        job_type: str  = job.get("type", "tts")
        label = job.get("text", wav_path.name)[:40] if job_type == "tts" else wav_path.name

        if not wav_path.exists():
            log.warning(f"ファイルが存在しません: {wav_path}")
            return

        if not self.bot.voice_client or not self.bot.voice_client.is_connected():
            log.warning("ボイスクライアント未接続。スキップします。")
            return

        self._done_event.clear()
        source = discord.FFmpegPCMAudio(str(wav_path))

        def _after(err):
            if err:
                log.error(f"再生エラー: {err}")
            asyncio.get_event_loop().call_soon_threadsafe(self._done_event.set)

        self.bot.play_audio(source, after_callback=_after)
        await self._push_status("playing", label)
        log.info(f"再生開始: [{job_type}] {label}")

        await self._done_event.wait()
        await self._push_status("idle", "")
        log.info(f"再生完了: {label}")

    async def _push_status(self, event: str, detail: str = ""):
        try:
            self.status_queue.put_nowait({"event": event, "detail": detail})
        except asyncio.QueueFull:
            pass
