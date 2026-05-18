"""
TtsWorker: tts_queue からテキストを取り出し、
VOICEVOX で WAV 生成 → playback_queue に投入する
"""
import asyncio
import logging

from services.voicevox import VoicevoxService

log = logging.getLogger("tts_worker")

_voicevox = VoicevoxService()


class TtsWorker:
    def __init__(self, tts_queue: asyncio.Queue, playback_queue: asyncio.Queue, status_queue: asyncio.Queue):
        self.tts_queue      = tts_queue
        self.playback_queue = playback_queue
        self.status_queue   = status_queue

    async def run(self):
        log.info("TtsWorker 起動")
        while True:
            try:
                job = await self.tts_queue.get()
                text       = job["text"]
                speaker_id = job.get("speaker_id")
                speed      = job.get("speed", 1.0)
                pitch      = job.get("pitch", 0.0)

                await self._push_status("tts_generating", text[:30])
                wav_path = await _voicevox.synthesize(
                    text=text,
                    speaker_id=speaker_id,
                    speed=speed,
                    pitch=pitch,
                )
                await self.playback_queue.put({
                    "type":     "tts",
                    "wav_path": wav_path,
                    "text":     text,
                })
                log.info(f"playback_queue に投入: {wav_path.name}")
                self.tts_queue.task_done()

            except asyncio.CancelledError:
                log.info("TtsWorker 停止")
                break
            except Exception as e:
                log.error(f"TtsWorker エラー: {e}", exc_info=True)
                await asyncio.sleep(3)

    async def _push_status(self, event: str, detail: str = ""):
        try:
            self.status_queue.put_nowait({"event": event, "detail": detail})
        except asyncio.QueueFull:
            pass
