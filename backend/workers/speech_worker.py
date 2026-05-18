"""
SpeechWorker: speech_queue からトピックを取り出し、
ニュース取得 → LLM生成 → tts_queue に投入する
"""
import asyncio
import logging

from services.news_fetcher import build_context
from services.llm import generate_talk

log = logging.getLogger("speech_worker")


class SpeechWorker:
    def __init__(self, speech_queue: asyncio.Queue, tts_queue: asyncio.Queue, status_queue: asyncio.Queue):
        self.speech_queue = speech_queue
        self.tts_queue    = tts_queue
        self.status_queue = status_queue

    async def run(self):
        log.info("SpeechWorker 起動")
        while True:
            try:
                job = await self.speech_queue.get()
                topic        = job.get("topic", "最新テクノロジー")
                speaker_id   = job.get("speaker_id")
                speed        = job.get("speed", 1.0)
                pitch        = job.get("pitch", 0.0)

                await self._push_status("generating_talk", topic)
                log.info(f"トーク生成開始: {topic!r}")

                context = await build_context()
                text    = await generate_talk(topic=topic, context=context)

                await self.tts_queue.put({
                    "text":       text,
                    "speaker_id": speaker_id,
                    "speed":      speed,
                    "pitch":      pitch,
                })
                log.info(f"tts_queue に投入: {len(text)}文字")
                self.speech_queue.task_done()

            except asyncio.CancelledError:
                log.info("SpeechWorker 停止")
                break
            except Exception as e:
                log.error(f"SpeechWorker エラー: {e}", exc_info=True)
                await asyncio.sleep(3)

    async def _push_status(self, event: str, detail: str = ""):
        try:
            self.status_queue.put_nowait({"event": event, "detail": detail})
        except asyncio.QueueFull:
            pass
