"""
BgmWorker: bgm_prefetch_queue からクエリ/URLを取り出し、
yt-dlp で音楽をダウンロード → playback_queue に投入する。
- YouTube URL / YouTube Music URL の直接ダウンロードに対応
- クエリ未指定時: 30%の確率でYouTube Musicトレンド曲、残りはプリセット
- 曲再生前にアクティブキャラクターのボイスで曲名アナウンスを挿入
"""
import asyncio
import logging
import random

from services.ytdlp_service import get_bgm
from services.llm import pick_bgm_query

log = logging.getLogger("bgm_worker")

# ─── キャラクター別アナウンステンプレート ─────────────────────
_ANNOUNCE = {
    "haru": [
        "次の曲は「{title}」です！",
        "お届けするのは「{title}」！どうぞ！",
        "では「{title}」をお聴きください！",
    ],
    "ao": [
        "続きましては「{title}」です。",
        "次は「{title}」をお届けします。",
        "「{title}」、どうぞ。",
    ],
    "yuki": [
        "「{title}」でも流しときます。",
        "まあ「{title}」でも聴けば？",
        "次は「{title}」。文句言わないで。",
    ],
    "sora": [
        "わーい、「{title}」だっちゃ！なのだ！",
        "え、「{title}」！？聴いてみよーなのだ！",
        "「{title}」が来たのだー！",
    ],
    "rei": [
        "それでは「{title}」をお届けします。",
        "次の曲は「{title}」ということですね。",
        "「{title}」です。ごゆっくりどうぞ。",
    ],
}
_ANNOUNCE_DEFAULT = [
    "次の曲は「{title}」です。",
    "お届けするのは「{title}」。",
]


def _make_announce_text(title: str) -> tuple[str, int | None]:
    """現在アクティブなMCキャラクターのアナウンス文とspeaker_idを返す"""
    from services.character_manager import character_manager
    chars = character_manager.active()
    if not chars:
        return random.choice(_ANNOUNCE_DEFAULT).format(title=title), None

    # MC/進行役を優先、なければ最初のキャラ
    mc = next((c for c in chars if "MC" in c.role or "進行" in c.role), chars[0])
    templates = _ANNOUNCE.get(mc.id, _ANNOUNCE_DEFAULT)
    text = random.choice(templates).format(title=_trim_title(title))
    return text, mc.speaker_id


def _trim_title(title: str, max_len: int = 30) -> str:
    """長すぎるタイトルを省略（yt-dlpのタイトルは長いことがある）"""
    title = title.strip()
    if len(title) <= max_len:
        return title
    return title[:max_len] + "…"


async def _resolve_query(job: dict) -> str:
    """ジョブからBGMクエリ/URLを決定する"""
    q = job.get("query", "").strip()
    if q:
        return q  # ユーザー指定を最優先

    if random.random() < 0.3:
        try:
            from services.ytmusic_service import pick_trending_url
            url = await pick_trending_url(country="JP")
            if url:
                return url
        except Exception as e:
            log.debug(f"トレンド取得スキップ: {e}")

    return pick_bgm_query()


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
                self.idle_event.clear()

                query        = await _resolve_query(job)
                enqueue      = job.get("enqueue", True)
                user_request = job.get("user_request", False)   # ユーザー指定URLはフィルタースキップ

                await self._push_status("bgm_fetching", query[:60])
                log.info(f"BGM取得開始: {query!r} (user_request={user_request})")

                bgm_path, title = await get_bgm(query, user_request=user_request)

                if bgm_path and enqueue:
                    # ① アナウンスTTSを先にWAV生成してからキューへ
                    if title:
                        await self._enqueue_announce(title)

                    # ② BGM本体
                    await self.playback_queue.put({"type": "bgm", "wav_path": bgm_path})
                    log.info(f"BGM → playback_queue: {bgm_path.name} ({title!r})")
                    await self._push_status("bgm_ready", title or bgm_path.name)
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

    async def _enqueue_announce(self, title: str):
        """アナウンスWAVをVOICEVOXで生成してplayback_queueに先行投入する"""
        try:
            from services.voicevox import VoicevoxService
            text, speaker_id = _make_announce_text(title)
            log.info(f"曲アナウンス生成: {text!r} (speaker={speaker_id})")
            vv  = VoicevoxService()
            wav = await vv.synthesize(text=text, speaker_id=speaker_id)
            await self.playback_queue.put({"type": "tts", "wav_path": wav, "text": text})
        except Exception as e:
            log.warning(f"アナウンス生成スキップ: {e}")

    async def _push_status(self, event: str, detail: str = ""):
        try:
            self.status_queue.put_nowait({"event": event, "detail": detail})
        except asyncio.QueueFull:
            pass

