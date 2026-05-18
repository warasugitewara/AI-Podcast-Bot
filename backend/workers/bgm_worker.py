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
from services.voicevox import VoicevoxService

log = logging.getLogger("bgm_worker")

_voicevox = VoicevoxService()   # シングルトン（毎回newしない）

# ─── キャラクター別アナウンステンプレート ─────────────────────
# 理由なし版
_ANNOUNCE: dict[str, list[str]] = {
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
        "「{title}」を流します。",
        "次は「{title}」。",
        "「{title}」でも聴いてください。",
    ],
    "sora": [
        "次は「{title}」！",
        "「{title}」、聴いてみましょう！",
        "お次は「{title}」です！",
    ],
    "rei": [
        "それでは「{title}」をお届けします。",
        "次の曲は「{title}」です。",
        "「{title}」です。ごゆっくりどうぞ。",
    ],
}
_ANNOUNCE_DEFAULT = [
    "次の曲は「{title}」です。",
    "お届けするのは「{title}」。",
]

# 理由あり版
_ANNOUNCE_REASON: dict[str, list[str]] = {
    "haru": [
        "{reason}「{title}」をどうぞ！",
        "{reason}次は「{title}」です！",
    ],
    "ao": [
        "{reason}「{title}」をお届けします。",
        "{reason}次は「{title}」です。",
    ],
    "yuki": [
        "{reason}「{title}」を流します。",
        "{reason}「{title}」にしました。",
    ],
    "sora": [
        "{reason}「{title}」にしましょう！",
        "{reason}「{title}」はどうですか！",
    ],
    "rei": [
        "{reason}「{title}」をお届けします。",
        "{reason}「{title}」です。ごゆっくりどうぞ。",
    ],
}
_ANNOUNCE_REASON_DEFAULT = [
    "{reason}「{title}」をお届けします。",
    "{reason}次は「{title}」です。",
]

# 曲後コメントテンプレート
_POST_COMMENT: dict[str, list[str]] = {
    "haru": [
        "「{title}」でした！良かったですね！",
        "「{title}」どうでしたか？",
        "いやー「{title}」、よかったです！",
    ],
    "ao": [
        "「{title}」でした。",
        "以上、「{title}」をお届けしました。",
    ],
    "yuki": [
        "「{title}」でした。悪くないです。",
        "「{title}」か。うん、まあよかったんじゃないですか。",
    ],
    "sora": [
        "「{title}」でした！なんか気持ちよかったです！",
        "いい曲でした、「{title}」！",
    ],
    "rei": [
        "「{title}」でした。少し気持ちが落ち着きましたね。",
        "ありがとうございました。「{title}」でした。",
    ],
    "ken": [
        "「{title}」最高でした！",
        "いやー熱い！「{title}」！",
    ],
    "nana": [
        "「{title}」元気出てきましたね！",
        "「{title}」よかったです！みんなも元気になれたかな？",
    ],
    "zona": [
        "「{title}」でした！テンション上がりましたね！",
        "「{title}」！最高の一曲でした！",
    ],
    "sayo": [
        "「{title}」でした。",
        "音が終わりました。「{title}」。",
    ],
    "shiro": [
        "「{title}」って言うんですね。へえ〜。",
        "「{title}」でしたよ。合ってましたか？",
    ],
    "nia": [
        "「{title}」……なんかふわふわしました。",
        "「{title}」は不思議な感じがしましたね。",
    ],
    "maron": [
        "「{title}」でした。みなさんもゆっくりできましたか？",
        "「{title}」、癒されましたね。",
    ],
    "nurse": [
        "「{title}」でした。適切な選曲だったと思います。",
        "「{title}」。再生終了です。",
    ],
}
_POST_COMMENT_DEFAULT = [
    "「{title}」でした。",
    "以上、「{title}」をお届けしました。",
]


def _make_announce_text(title: str) -> tuple[str, int | None]:
    """現在アクティブなMCキャラクターのアナウンス文とspeaker_idを返す"""
    from services.character_manager import character_manager
    from services.program_memory import program_memory
    chars = character_manager.active()
    if not chars:
        return random.choice(_ANNOUNCE_DEFAULT).format(title=_trim_title(title)), None

    # MC/進行役を優先、なければ最初のキャラ
    mc = next((c for c in chars if "MC" in c.role or "進行" in c.role), chars[0])
    trimmed = _trim_title(title)
    reason  = program_memory.bgm_reason()

    if reason:
        templates = _ANNOUNCE_REASON.get(mc.id, _ANNOUNCE_REASON_DEFAULT)
        text = random.choice(templates).format(title=trimmed, reason=reason)
    else:
        templates = _ANNOUNCE.get(mc.id, _ANNOUNCE_DEFAULT)
        text = random.choice(templates).format(title=trimmed)

    return text, mc.speaker_id


def _trim_title(title: str, max_len: int = 30) -> str:
    """長すぎるタイトルを省略（yt-dlpのタイトルは長いことがある）"""
    title = title.strip()
    if len(title) <= max_len:
        return title
    return title[:max_len] + "…"


async def _resolve_query(job: dict) -> str:
    """ジョブからBGMクエリ/URLを決定する（マルチソース・アンチリピート対応）"""
    q = job.get("query", "").strip()
    if q:
        return q  # ユーザー指定を最優先

    from services.program_memory import program_memory

    r = random.random()

    # 25%: YouTube Music トレンド JP
    if r < 0.25:
        try:
            from services.ytmusic_service import pick_trending_url
            url = await pick_trending_url(country="JP")
            if url and not program_memory.is_recent_bgm_query(url):
                program_memory.add_bgm_query(url)
                return url
        except Exception as e:
            log.debug(f"JPトレンド取得スキップ: {e}")

    # 25%〜40%: YouTube Music トレンド US / KR ランダム
    elif r < 0.40:
        try:
            from services.ytmusic_service import pick_trending_url
            country = random.choice(["US", "KR", "GB"])
            url = await pick_trending_url(country=country)
            if url and not program_memory.is_recent_bgm_query(url):
                program_memory.add_bgm_query(url)
                log.info(f"海外トレンド選曲 ({country})")
                return url
        except Exception as e:
            log.debug(f"海外トレンド取得スキップ: {e}")

    # 残り60%: プリセットプール（最近使用済みを除外・最大10回試す）
    for _ in range(10):
        candidate = pick_bgm_query()
        if not program_memory.is_recent_bgm_query(candidate):
            program_memory.add_bgm_query(candidate)
            return candidate

    # フォールバック（全部最近使用済みの場合はそのまま使う）
    fallback = pick_bgm_query()
    program_memory.add_bgm_query(fallback)
    return fallback


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
                    # BGMジャンルを番組メモリに記録
                    from services.program_memory import program_memory
                    program_memory.add_genre(query)

                    # ① 曲前アナウンスTTSを先に投入
                    if title:
                        await self._enqueue_announce(title)

                    # ② BGM本体
                    await self.playback_queue.put({"type": "bgm", "wav_path": bgm_path})
                    log.info(f"BGM → playback_queue: {bgm_path.name} ({title!r})")
                    await self._push_status("bgm_ready", title or bgm_path.name)

                    # ③ 曲後コメント（30%の確率で挿入）
                    if title:
                        await self._enqueue_post_comment(title)
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
        """アナウンスWAVをVOICEVOXで生成してplayback_queueに先行投入する。
        失敗時は別スピーカー(フォールバック)で1回リトライする。"""
        from services.voicevox import VoicevoxService
        text, speaker_id = _make_announce_text(title)
        log.info(f"曲アナウンス生成: {text!r} (speaker={speaker_id})")
        vv = VoicevoxService()
        # voicevox.py 内で3回リトライ済み。それでも失敗した場合は別speakerで再試行
        for sid in [speaker_id, 3, 8]:  # ずんだもん→春日部つむぎ にフォールバック
            try:
                wav = await vv.synthesize(text=text, speaker_id=sid)
                await self.playback_queue.put({"type": "tts", "wav_path": wav, "text": text})
                return
            except Exception as e:
                log.warning(f"アナウンス生成スキップ (speaker={sid}): {e}")

    async def _enqueue_post_comment(self, title: str):
        """曲後コメントWAVを生成してplayback_queueに投入する（30%の確率で実行）。"""
        if random.random() > 0.30:
            return
        try:
            from services.character_manager import character_manager
            from services.voicevox import VoicevoxService
            chars = character_manager.active()
            if not chars:
                return
            mc = next((c for c in chars if "MC" in c.role or "進行" in c.role), chars[0])
            trimmed = _trim_title(title)
            templates = _POST_COMMENT.get(mc.id, _POST_COMMENT_DEFAULT)
            text = random.choice(templates).format(title=trimmed)
            log.info(f"曲後コメント生成: {text!r} (speaker={mc.speaker_id})")
            vv = VoicevoxService()
            for sid in [mc.speaker_id, 3, 8]:
                try:
                    wav = await vv.synthesize(text=text, speaker_id=sid)
                    await self.playback_queue.put({"type": "tts", "wav_path": wav, "text": text})
                    return
                except Exception as e:
                    log.warning(f"曲後コメント生成スキップ (speaker={sid}): {e}")
        except Exception as e:
            log.warning(f"曲後コメントスキップ: {e}")

    async def _push_status(self, event: str, detail: str = ""):
        try:
            self.status_queue.put_nowait({"event": event, "detail": detail})
        except asyncio.QueueFull:
            pass

