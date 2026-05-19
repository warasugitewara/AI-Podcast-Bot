"""
ContentScheduler: 台本生成・音楽ブレイクのスケジューリング管理

フロー（パイプライン化済み）:
  ┌─ 音楽ブレイク時 ─────────────────────────────────────────┐
  │ idle待ち → BGM投入 → BGM再生中に PREFETCH_COUNT 分先読み │
  │ → 音楽終了後すぐにコンテンツ再生（無音なし）              │
  └───────────────────────────────────────────────────────────┘
  ┌─ 通常エピソード間 ────────────────────────────────────────┐
  │ tts_queue が空になったら即LLM生成開始                      │
  │ → 前エピソード再生中に次エピソードを合成                   │
  │ → 前エピソード終了時に次がすでに再生キューに積まれている   │
  └───────────────────────────────────────────────────────────┘

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
from services.program_memory import program_memory
from config import NIM_MIN_INTERVAL_SEC

log = logging.getLogger("content_scheduler")

MIN_LLM_INTERVAL = NIM_MIN_INTERVAL_SEC   # .env で上書き可能、デフォルト120秒
MUSIC_EVERY_N    = 3     # N回対話ごとに音楽ブレイク
PREFETCH_COUNT   = 3     # 音楽中に先読み生成するエピソード数
MAX_BACKOFF      = 600   # 最大バックオフ(秒)
TTS_PIPELINE_MAX = 1     # tts_queue がこの数以下になったら次の生成を開始


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

                # ── 優先1: ユーザー音楽リクエスト ──────────────
                try:
                    req = self.music_request_queue.get_nowait()
                    self.music_request_queue.task_done()
                    # tts_queue + playback_queue 両方空になってから挿入
                    await self._wait_full_idle()
                    await self._trigger_music(
                        req["query"],
                        label=req.get("title", req["query"]),
                        user_request=req.get("user_request", False),
                    )
                    # 曲が終わるまで待つ。continueしない → 必ずトークを1エピソード挟む
                    # （次のリクエストは次のループ先頭で優先1として拾われる）
                    await self._wait_full_idle()
                except asyncio.QueueEmpty:
                    pass

                # ── 優先2: 定期音楽ブレイク ─────────────────────
                if self._episode_count > 0 and self._episode_count % MUSIC_EVERY_N == 0:
                    log.info(f"音楽ブレイク ({self._episode_count}エピソード完了)")
                    # tts_queue + playback_queue が両方空になってから音楽へ
                    await self._wait_full_idle()
                    await self._trigger_music("", label="自動選曲中")
                    self._episode_count = 0

                    # ── 音楽ブレイク時にキャストを自動ローテーション ──
                    from services.character_manager import character_manager
                    new_cast = character_manager.shuffle()
                    log.info(f"キャスト自動ローテーション → {new_cast['label']}")
                    await self._push_status("cast_rotated", new_cast["label"])

                    # ── BGM再生中に先読み生成 ─────────────────
                    # episode_count は先読み分をカウントしない（次の音楽ブレイクは
                    # メインループで通常生成した分だけで判定する）
                    await self._prefetch_during_bgm(PREFETCH_COUNT)

                    # 先読み分 + BGM が全て終わるまで待ってから次のループへ
                    await self._wait_full_idle()
                    continue

                # ── 優先3: 手動/自動トーク (パイプライン) ───────
                # tts_queue が閾値以下になったら即生成（前エピソード再生中でもOK）
                await self._wait_tts_slot()

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
                    if self.idle_event.is_set() and self.tts_queue.qsize() == 0:
                        log.info("クールタイム中 → BGMを自動挿入")
                        await self._trigger_music("", label="BGM（クールタイム中）")

                    # カウントダウン（途中でアイドルになってもBGM追加挿入）
                    deadline = time.monotonic() + remaining
                    while True:
                        left = deadline - time.monotonic()
                        if left <= 0:
                            break
                        await self._push_status("cooldown", f"{left:.0f}秒")
                        # 無音になったら追加BGM
                        if self.idle_event.is_set() and self.tts_queue.qsize() == 0:
                            log.info("クールタイム中に無音検知 → BGM追加挿入")
                            await self._trigger_music("", label="BGM（クールタイム中）")
                        await asyncio.sleep(min(5.0, left))

                # 生成前にビジーマーク
                self.idle_event.clear()

                await self._generate(job)
                self._last_gen_time = time.monotonic()
                self._episode_count += 1

            except asyncio.CancelledError:
                log.info("ContentScheduler 停止")
                break
            except Exception as e:
                log.error(f"ContentScheduler エラー: {e}", exc_info=True)
                self.idle_event.set()
                await asyncio.sleep(10)

    # ─── パイプライン待機 ──────────────────────────────────────
    async def _wait_tts_slot(self):
        """tts_queue が閾値以下になるまで待機（パイプライン制御）"""
        waited = False
        while self.tts_queue.qsize() > TTS_PIPELINE_MAX:
            if not waited:
                log.debug(f"tts_queue={self.tts_queue.qsize()} → 先行合成待ち")
                waited = True
            await asyncio.sleep(0.5)

    async def _wait_full_idle(self):
        """tts_queue・playback_queue の両方が空になるまで待機
        (idle_event は playback_queue のみ監視するため、tts_queue も別途確認)
        """
        while True:
            if self.tts_queue.qsize() == 0 and self.idle_event.is_set():
                break
            await asyncio.sleep(0.5)

    # ─── BGM中先読み ──────────────────────────────────────────
    async def _prefetch_during_bgm(self, count: int):
        """BGM 再生中に最大 count エピソードを先読み生成する
        ※ _episode_count はここでは加算しない（音楽ブレイクタイミングに影響させない）
        """
        log.info(f"BGM中先読み開始: 最大{count}エピソード生成します")
        generated = 0
        for i in range(count):
            if not self.broadcast_active.is_set():
                log.info("放送非アクティブのため先読み中断")
                break

            # NIM クールタイム遵守
            elapsed   = time.monotonic() - self._last_gen_time
            remaining = max(0.0, self._backoff - elapsed)
            if remaining > 0:
                log.info(f"BGM先読み {i+1}/{count}: NIMクールタイム {remaining:.0f}秒待機")
                await self._push_status("cooldown", f"先読み待機 {remaining:.0f}秒")
                await asyncio.sleep(remaining)

            # ユーザーリクエストが来たら先読み中断して優先
            try:
                req = self.music_request_queue.get_nowait()
                self.music_request_queue.task_done()
                log.info("先読み中にユーザー音楽リクエスト → 先読み中断")
                await self._trigger_music(
                    req["query"],
                    label=req.get("title", req["query"]),
                    user_request=req.get("user_request", False),
                )
                break
            except asyncio.QueueEmpty:
                pass

            try:
                job = {"topic": "", "auto": True}
                try:
                    job = self.speech_queue.get_nowait()
                    self.speech_queue.task_done()
                except asyncio.QueueEmpty:
                    pass

                log.info(f"BGM先読み {i+1}/{count}: 台本生成中...")
                await self._push_status("generating", f"BGM先読み {i+1}/{count}")
                await self._generate(job)
                self._last_gen_time = time.monotonic()
                generated += 1
                log.info(f"BGM先読み {i+1}/{count} 完了 (計{generated}本生成)")

            except Exception as e:
                log.warning(f"BGM先読み {i+1} エラー: {e}")
                break

        log.info(f"BGM中先読み終了: {generated}/{count}エピソード生成")

    # ─── 音楽トリガー ─────────────────────────────────────────
    async def _trigger_music(self, query: str, label: str = "", user_request: bool = False):
        self.idle_event.clear()
        await self._push_status("music_queuing", label or query or "選曲中")
        log.info(f"音楽リクエスト → bgm_queue: {query!r}")
        await self.bgm_queue.put({"query": query, "context": "", "enqueue": True, "user_request": user_request})

    # ─── 台本生成 ─────────────────────────────────────────────
    async def _generate(self, job: dict):
        topic = job.get("topic", "").strip()
        await self._push_status("generating", topic or "自動生成中...")
        try:
            context = await build_context()
            chars   = character_manager.active()
            memory_ctx = program_memory.context_summary()
            # contextがある（ニュース系）場合はnewsモード、それ以外はchat
            mode = job.get("mode", "news" if context else "chat")
            lines, resolved_topic = await generate_dialogue(
                topic=topic, context=context, chars=chars, memory_ctx=memory_ctx, mode=mode
            )

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
                # mode別デフォルト速度: news=0.93(落ち着き)、chat=1.05(テンポよく)
                _MODE_SPEED = {"news": 0.93, "chat": 1.05, "transition": 1.0}
                speed = job.get("speed", _MODE_SPEED.get(mode, 1.0))
                pitch = job.get("pitch", 0.0)
                for line in lines:
                    sid = character_manager.speaker_id_for(line["speaker"])
                    await self.tts_queue.put({
                        "text": line["text"], "speaker_id": sid,
                        "speed": speed, "pitch": pitch,
                    })
                # 番組メモリに今回のトピックを記録
                program_memory.add_topic(resolved_topic)
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
