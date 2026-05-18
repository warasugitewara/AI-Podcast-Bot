"""
AI Podcast Bot バックエンド エントリーポイント
asyncio.Queue x4 + ワーカー起動 + Discord Bot + aiohttp APIサーバー
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

# ─── ログ設定 ──────────────────────────────────────────
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
    # ─── キュー定義 ──────────────────────────────────────
    speech_queue    = asyncio.Queue(maxsize=10)
    tts_queue       = asyncio.Queue(maxsize=10)
    playback_queue  = asyncio.Queue(maxsize=10)
    bgm_prefetch_q  = asyncio.Queue(maxsize=5)

    # SSE用ステータスキュー (frontendへ)
    status_queue = asyncio.Queue(maxsize=50)

    # ─── ワーカーとBot ────────────────────────────────────
    bot     = RadioBot(speech_queue, playback_queue, bgm_prefetch_q, status_queue)
    speech  = SpeechWorker(speech_queue, tts_queue, status_queue)
    tts     = TtsWorker(tts_queue, playback_queue, status_queue)
    playback= PlaybackWorker(playback_queue, bot, status_queue)
    bgm     = BgmWorker(bgm_prefetch_q, playback_queue, status_queue)

    # ─── aiohttp APIサーバー (frontendからのコマンド受信) ──
    from api_server import build_app
    app = build_app(bot, speech_queue, bgm_prefetch_q, status_queue)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", BACKEND_API_PORT)
    await site.start()
    log.info(f"APIサーバー起動: http://127.0.0.1:{BACKEND_API_PORT}")

    # ─── タスク起動 ──────────────────────────────────────
    tasks = [
        asyncio.create_task(speech.run(),   name="speech_worker"),
        asyncio.create_task(tts.run(),      name="tts_worker"),
        asyncio.create_task(playback.run(), name="playback_worker"),
        asyncio.create_task(bgm.run(),      name="bgm_worker"),
        asyncio.create_task(bot.start_bot(),name="discord_bot"),
    ]
    log.info("全ワーカー起動完了")

    # Graceful shutdown
    loop = asyncio.get_running_loop()
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
