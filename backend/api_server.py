"""
aiohttp ベースの内部 API サーバー (127.0.0.1 のみ)
Bun/Hono フロントエンドからのコマンドを受け付け、
各キューに投入する。SSE でステータスをストリーミング配信。
"""
import asyncio
import json
import logging
from aiohttp import web

log = logging.getLogger("api_server")


def build_app(bot, speech_queue, bgm_prefetch_q, status_queue) -> web.Application:
    app = web.Application()

    # ─── SSE: ステータスストリーミング ──────────────────────
    async def sse_status(request: web.Request):
        resp = web.StreamResponse(headers={
            "Content-Type":  "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })
        await resp.prepare(request)

        listeners: list = request.app.setdefault("sse_listeners", [])
        q: asyncio.Queue = asyncio.Queue()
        listeners.append(q)
        try:
            while True:
                msg = await q.get()
                data = json.dumps(msg, ensure_ascii=False)
                await resp.write(f"data: {data}\n\n".encode())
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            listeners.remove(q)
        return resp

    # ─── ステータスブロードキャスト (background task) ────────
    async def _broadcast_status(app: web.Application):
        while True:
            try:
                msg = await status_queue.get()
                for q in list(app.get("sse_listeners", [])):
                    try:
                        q.put_nowait(msg)
                    except asyncio.QueueFull:
                        pass
            except asyncio.CancelledError:
                break

    async def on_startup(app: web.Application):
        app["broadcast_task"] = asyncio.create_task(_broadcast_status(app))

    async def on_cleanup(app: web.Application):
        app["broadcast_task"].cancel()
        await asyncio.gather(app["broadcast_task"], return_exceptions=True)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # ─── REST エンドポイント ─────────────────────────────────
    async def post_talk(request: web.Request):
        """トークをキューに追加"""
        body = await request.json()
        await speech_queue.put({
            "topic":      body.get("topic", "最新テクノロジー"),
            "speaker_id": body.get("speaker_id"),
            "speed":      body.get("speed", 1.0),
            "pitch":      body.get("pitch", 0.0),
        })
        return web.json_response({"ok": True, "queued": "talk"})

    async def post_bgm(request: web.Request):
        """BGMリクエストをキューに追加"""
        body = await request.json()
        await bgm_prefetch_q.put({
            "query":   body.get("query", ""),
            "context": body.get("context", ""),
            "enqueue": body.get("enqueue", True),
        })
        return web.json_response({"ok": True, "queued": "bgm"})

    async def post_stop(request: web.Request):
        """現在の再生を停止"""
        bot.stop()
        return web.json_response({"ok": True, "action": "stop"})

    async def get_status(request: web.Request):
        """現在の状態をスナップショットで返す"""
        return web.json_response({
            "is_playing":   bot.is_playing(),
            "speech_queue": speech_queue.qsize(),
            "bgm_queue":    bgm_prefetch_q.qsize(),
        })

    async def get_speakers(request: web.Request):
        """VOICEVOXの話者一覧を返す"""
        from services.voicevox import VoicevoxService
        try:
            speakers = await VoicevoxService().get_speakers()
            return web.json_response(speakers)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=502)

    app.router.add_get("/status",    get_status)
    app.router.add_get("/speakers",  get_speakers)
    app.router.add_get("/sse",       sse_status)
    app.router.add_post("/talk",     post_talk)
    app.router.add_post("/bgm",      post_bgm)
    app.router.add_post("/stop",     post_stop)

    return app
