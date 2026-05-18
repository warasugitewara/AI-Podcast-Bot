"""
AI Podcast Bot バックエンド エントリーポイント
"""
import asyncio
import logging
import signal
import sys
from aiohttp import web

from config import BACKEND_API_PORT, LOGS_DIR
from discord_bot import RadioBot
from workers.speech_worker import SpeechWorker
from workers.tts_worker import TtsWorker
from workers.playback_worker import PlaybackWorker
from workers.bgm_worker import BgmWorker

LOGS_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGS_DIR / "backend.log"),
    ],
)
log = logging.getLogger("main")


async def main():
    # ─── キュー＆イベント定義 ──────────────────────────────
    speech_queue         = asyncio.Queue(maxsize=10)
    tts_queue            = asyncio.Queue(maxsize=20)
    playback_queue       = asyncio.Queue(maxsize=20)
    bgm_prefetch_q       = asyncio.Queue(maxsize=5)
    music_request_queue  = asyncio.Queue(maxsize=20)
    status_queue         = asyncio.Queue(maxsize=50)

    # 再生アイドル状態フラグ（Set=アイドル, Clear=再生/生成中）
    playback_idle = asyncio.Event()
    playback_idle.set()

    # 放送アクティブフラグ（Set=放送中, Clear=VC空室停止中）
    broadcast_active = asyncio.Event()
    broadcast_active.set()

    # ─── ワーカー・Bot ────────────────────────────────────
    bot      = RadioBot(speech_queue, playback_queue, bgm_prefetch_q,
                        music_request_queue, status_queue, broadcast_active)
    speech   = SpeechWorker(speech_queue, tts_queue, bgm_prefetch_q,
                            music_request_queue, status_queue, playback_idle,
                            broadcast_active)
    tts      = TtsWorker(tts_queue, playback_queue, status_queue)
    playback = PlaybackWorker(playback_queue, bot, status_queue, playback_idle)
    bgm      = BgmWorker(bgm_prefetch_q, playback_queue, status_queue, playback_idle)

    # BotからPlaybackWorkerを参照できるようにする（/volumeコマンド用）
    bot.playback_worker = playback

    # ─── API サーバー ─────────────────────────────────────
    from api_server import build_app
    app    = build_app(bot, speech_queue, tts_queue, bgm_prefetch_q,
                       music_request_queue, status_queue, speech, playback)
    runner = web.AppRunner(app)
    await runner.setup()
    site   = web.TCPSite(runner, "127.0.0.1", BACKEND_API_PORT)
    await site.start()
    log.info(f"APIサーバー起動: http://127.0.0.1:{BACKEND_API_PORT}")

    # ─── タスク起動 ──────────────────────────────────────
    tasks = [
        asyncio.create_task(speech.run(),    name="content_scheduler"),
        asyncio.create_task(tts.run(),       name="tts_worker"),
        asyncio.create_task(playback.run(),  name="playback_worker"),
        asyncio.create_task(bgm.run(),       name="bgm_worker"),
        asyncio.create_task(bot.start_bot(), name="discord_bot"),
    ]
    log.info("全ワーカー起動完了")

    loop       = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown(*_):
        log.info("シャットダウン要求を受信")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    await stop_event.wait()
    log.info("シャットダウン中...")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await runner.cleanup()
    log.info("シャットダウン完了")


if __name__ == "__main__":
    asyncio.run(main())
