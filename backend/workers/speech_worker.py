"""
ContentScheduler: 台本生成・音楽ブレイクのスケジューリング管理

優先順位:
  1. ユーザー音楽リクエスト (music_request_queue)
  2. 定期音楽ブレイク (MUSIC_EVERY_N エピソードごと)
  3. 手動トピックリクエスト (speech_queue)
  4. 自動生成
"""
from __future__ import annotations
import asyncio
import logging
import time

from services.news_fetcher import build_context
from services.llm import generate_talk, generate_dialogue, pick_bgm_query, get_daily_usage
from services.character_manager import character_manager
from config import NIM_MIN_INTERVAL_SEC

log = logging.getLogger("content_scheduler")

MIN_LLM_INTERVAL = NIM_MIN_INTERVAL_SEC   # .env で上書き可能、デフォルト120秒
MUSIC_EVERY_N    = 3     # N回対話ごとに音楽ブレイク
MAX_BACKOFF      = 600   # 最大バックオフ(秒)


class SpeechWorker:   # 後方互換でクラス名は維持
    def __init__(
        self,
        speech_queue:         asyncio.Queue,
        tts_queue:            asyncio.Queue,
        bgm_queue:            asyncio.Queue,
        music_request_queue:  asyncio.Queue,
        status_queue:         asyncio.Queue,
        idle_event:           asyncio.Event,
        broadcast_active:     asyncio.Event,
    ):
        self.speech_queue        = speech_queue
        self.tts_queue           = tts_queue
        self.bgm_queue           = bgm_queue
        self.music_request_queue = music_request_queue
        self.status_queue        = status_queue
        self.idle_event          = idle_event
        self.broadcast_active    = broadcast_active

        self._last_gen_time  = 0.0
        self._episode_count  = 0
        self._backoff        = float(MIN_LLM_INTERVAL)

    async def run(self):
        log.info("ContentScheduler 起動")
        while True:
            try:
                # VC空室中は新規生成しない（LLMコールとTTS生成を節約）
                await self.broadcast_active.wait()

                await self.idle_event.wait()

                # ── 優先1: ユーザー音楽リクエスト ──────────────
                try:
                    req = self.music_request_queue.get_nowait()
                    self.music_request_queue.task_done()
                    await self._trigger_music(req["query"], label=req.get("title", req["query"]))
                    continue
                except asyncio.QueueEmpty:
                    pass

                # ── 優先2: 定期音楽ブレイク ─────────────────────
                if self._episode_count > 0 and self._episode_count % MUSIC_EVERY_N == 0:
                    log.info(f"音楽ブレイク ({self._episode_count}エピソード完了)")
                    await self._trigger_music("", label="自動選曲中")
                    self._episode_count = 0
                    continue

                # ── 優先3: 手動/自動トーク ──────────────────────
                try:
                    job = self.speech_queue.get_nowait()
                    self.speech_queue.task_done()
                except asyncio.QueueEmpty:
                    job = {"topic": "", "mode": "dialogue", "auto": True}

                # ── クールタイム ────────────────────────────────
                elapsed   = time.monotonic() - self._last_gen_time
                remaining = self._backoff - elapsed
                if remaining > 0:
                    log.info(f"クールタイム待機: {remaining:.0f}秒")
                    await self._push_status("cooldown", f"{remaining:.0f}秒")

                    # アイドル中ならBGMで無音を埋める
                    if self.idle_event.is_set():
                        log.info("クールタイム中 → BGMを自動挿入")
                        await self._trigger_music("", label="BGM（クールタイム中）")

                    # クールタイムを1秒ごとにカウントダウン更新
                    deadline = time.monotonic() + remaining
                    while True:
                        left = deadline - time.monotonic()
                        if left <= 0:
                            break
                        await self._push_status("cooldown", f"{left:.0f}秒")
                        await asyncio.sleep(min(5.0, left))

                # 生成前にビジーマーク（race condition防止）
                self.idle_event.clear()

                await self._generate(job)
                self._last_gen_time = time.monotonic()
                self._episode_count += 1

            except asyncio.CancelledError:
                log.info("ContentScheduler 停止")
                break
            except Exception as e:
                log.error(f"ContentScheduler エラー: {e}", exc_info=True)
                self.idle_event.set()   # エラー時はidleに戻す
                await asyncio.sleep(10)

    # ─── 音楽トリガー ─────────────────────────────────────────
    async def _trigger_music(self, query: str, label: str = ""):
        self.idle_event.clear()
        await self._push_status("music_queuing", label or query or "選曲中")
        log.info(f"音楽リクエスト → bgm_queue: {query!r}")
        await self.bgm_queue.put({"query": query, "context": "", "enqueue": True})

    # ─── 台本生成 ─────────────────────────────────────────────
    async def _generate(self, job: dict):
        topic = job.get("topic", "").strip()
        await self._push_status("generating", topic or "自動生成中...")
        try:
            context = await build_context()
            chars   = character_manager.active()
            lines   = await generate_dialogue(topic=topic, context=context, chars=chars)

            if not lines:
                # 日次上限到達またはパース失敗 → 音楽にフォールバック（LLMコール節約）
                usage = get_daily_usage()
                if usage["used"] >= usage["limit"]:
                    log.warning(f"NIM日次上限({usage['limit']}件)到達。音楽にフォールバック")
                    await self._push_status("daily_limit", f"{usage['used']}/{usage['limit']}")
                    await self.bgm_queue.put({"query": pick_bgm_query(), "enqueue": True})
                    return
                log.warning("台本が空。ソロにフォールバック")
                text = await generate_talk(topic=topic, context=context)
                if text:
                    await self.tts_queue.put({
                        "text": text,
                        "speaker_id": chars[0].speaker_id if chars else None,
                        "speed": 1.0, "pitch": 0.0,
                    })
            else:
                speed = job.get("speed", 1.0)
                pitch = job.get("pitch", 0.0)
                for line in lines:
                    sid = character_manager.speaker_id_for(line["speaker"])
                    await self.tts_queue.put({
                        "text": line["text"], "speaker_id": sid,
                        "speed": speed, "pitch": pitch,
                    })
                log.info(f"対話 {len(lines)}行 → tts_queue "
                         f"cast={character_manager.cast_name} "
                         f"{[c.name for c in chars]}")

            # 成功 → バックオフリセット
            self._backoff = float(MIN_LLM_INTERVAL)

        except Exception as e:
            err_str = str(e).lower()
            if "429" in str(e) or "rate_limit" in err_str or "too many requests" in err_str:
                self._backoff = min(self._backoff * 2, MAX_BACKOFF)
                log.warning(f"レートリミット。次のバックオフ: {self._backoff:.0f}秒")
                await self._push_status("rate_limited", f"バックオフ{self._backoff:.0f}秒")
            self.idle_event.set()
            raise

    async def _push_status(self, event: str, detail: str = ""):
        try:
            self.status_queue.put_nowait({"event": event, "detail": detail})
        except asyncio.QueueFull:
            pass
