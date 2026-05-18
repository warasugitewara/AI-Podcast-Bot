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


def build_app(bot, speech_queue, tts_queue, bgm_prefetch_q, music_request_queue, status_queue, scheduler=None, playback=None) -> web.Application:
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

    async def post_music(request: web.Request):
        """ユーザー音楽リクエストをキューに追加"""
        body = await request.json()
        query = body.get("query", "").strip()
        if not query:
            return web.json_response({"ok": False, "error": "query is required"}, status=400)
        await music_request_queue.put({
            "query": query,
            "title": body.get("title", query),
            "user_request": True,
        })
        return web.json_response({"ok": True, "queued": "music", "query": query})

    async def get_bgm_volume(request: web.Request):
        """BGM音量を返す"""
        vol = playback.bgm_volume if playback else 0.8
        return web.json_response({"volume": round(vol, 2)})

    async def post_bgm_volume(request: web.Request):
        """BGM音量を変更する (0.0〜2.0)"""
        if playback is None:
            return web.json_response({"ok": False, "error": "playback not available"}, status=503)
        body  = await request.json()
        value = body.get("volume")
        if value is None:
            return web.json_response({"ok": False, "error": "volume is required"}, status=400)
        try:
            vol = float(value)
        except (TypeError, ValueError):
            return web.json_response({"ok": False, "error": "volume must be a number"}, status=400)
        vol = max(0.0, min(2.0, vol))
        playback.bgm_volume = vol
        log.info(f"BGM音量変更: {vol:.0%}")
        return web.json_response({"ok": True, "volume": round(vol, 2)})

    async def post_stop(request: web.Request):
        """現在の再生を停止"""
        bot.stop()
        return web.json_response({"ok": True, "action": "stop"})

    async def get_status(request: web.Request):
        """現在の状態をスナップショットで返す"""
        import time
        cooldown_remaining = 0
        if scheduler is not None:
            elapsed   = time.monotonic() - scheduler._last_gen_time
            remaining = scheduler._backoff - elapsed
            cooldown_remaining = max(0, round(remaining))
        return web.json_response({
            "is_playing":          bot.is_playing(),
            "broadcast_active":    bot.broadcast_active.is_set(),
            "speech_queue":        speech_queue.qsize(),
            "tts_queue":           tts_queue.qsize(),
            "bgm_queue":           bgm_prefetch_q.qsize(),
            "music_request_queue": music_request_queue.qsize(),
            "cooldown_remaining":  cooldown_remaining,
            "episode_count":       getattr(scheduler, "_episode_count", 0),
        })

    async def get_queue(request: web.Request):
        """音楽キューの詳細を返す（内部dequeをピーク）"""
        items = list(music_request_queue._queue)  # noqa: SLF001
        return web.json_response({
            "music": [
                {"query": i.get("query", ""), "title": i.get("title", i.get("query", ""))}
                for i in items
            ],
            "music_count":  music_request_queue.qsize(),
            "speech_count": speech_queue.qsize(),
            "tts_count":    tts_queue.qsize(),
        })

    async def get_casts_list(request: web.Request):
        """全キャスト一覧を返す"""
        from services.character_manager import CASTS, CHARACTERS, character_manager
        result = {}
        for key, cast in CASTS.items():
            result[key] = {
                "label":  cast["label"],
                "desc":   cast.get("desc", ""),
                "active": key == character_manager.cast_name,
                "chars": [
                    {"id": c, "name": CHARACTERS[c].name, "role": CHARACTERS[c].role}
                    for c in cast["chars"] if c in CHARACTERS
                ],
            }
        return web.json_response(result)

    async def get_trending(request: web.Request):
        """YouTube Music トレンド曲一覧を返す"""
        country = request.rel_url.query.get("country", "JP")
        try:
            from services.ytmusic_service import get_trending_songs
            songs = await get_trending_songs(country=country, limit=20)
            return web.json_response({"songs": songs, "country": country})
        except Exception as e:
            return web.json_response({"error": str(e), "songs": []}, status=500)

    async def get_speakers(request: web.Request):
        """VOICEVOXの話者一覧を返す"""
        from services.voicevox import VoicevoxService
        try:
            speakers = await VoicevoxService().get_speakers()
            return web.json_response(speakers)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=502)

    async def get_cast(request: web.Request):
        """現在のキャストを返す"""
        from services.character_manager import character_manager, CASTS
        chars = character_manager.active()
        cast_info = CASTS.get(character_manager.cast_name, {})
        return web.json_response({
            "cast_name":  character_manager.cast_name,
            "cast_label": cast_info.get("label", "カスタム"),
            "characters": [
                {"id": c.id, "name": c.name, "role": c.role,
                 "speaker_id": c.speaker_id, "speaker_name": c.speaker_name}
                for c in chars
            ],
        })

    async def post_cast(request: web.Request):
        """キャストを変更する"""
        from services.character_manager import character_manager
        body = await request.json()
        name = body.get("name", "").strip()
        if not name:
            return web.json_response({"ok": False, "error": "name is required"}, status=400)
        result = character_manager.set_cast(name)
        if result is None:
            return web.json_response({"ok": False, "error": f"cast '{name}' not found"}, status=404)
        return web.json_response({"ok": True, "cast_name": name, "cast_label": result["label"]})

    async def get_chars(request: web.Request):
        """キャラクター一覧を返す"""
        from services.character_manager import CHARACTERS
        return web.json_response([
            {"id": c.id, "name": c.name, "role": c.role,
             "speaker_id": c.speaker_id, "speaker_name": c.speaker_name,
             "style": c.style}
            for c in CHARACTERS.values()
        ])

    async def post_shuffle(request: web.Request):
        """キャストをランダム変更する"""
        from services.character_manager import character_manager
        result = character_manager.shuffle()
        return web.json_response({
            "ok": True,
            "cast_name":  character_manager.cast_name,
            "cast_label": result["label"],
        })

    async def post_cast_custom(request: web.Request):
        """任意のキャラIDリストでカスタムキャストを設定する
        body: {"char_ids": ["haru", "sayo", "shiro"]}
        """
        from services.character_manager import character_manager, CHARACTERS
        body     = await request.json()
        char_ids = body.get("char_ids", [])
        if not isinstance(char_ids, list) or len(char_ids) < 2:
            return web.json_response(
                {"ok": False, "error": "char_ids must be a list of 2+ character IDs"}, status=400
            )
        if len(char_ids) > 6:
            return web.json_response(
                {"ok": False, "error": "max 6 characters"}, status=400
            )
        unknown = [c for c in char_ids if c not in CHARACTERS]
        if unknown:
            return web.json_response(
                {"ok": False, "error": f"unknown character IDs: {unknown}"}, status=404
            )
        chars = character_manager.set_custom(char_ids)
        return web.json_response({
            "ok":   True,
            "cast_name":  "custom",
            "cast_label": "カスタム",
            "characters": [
                {"id": c.id, "name": c.name, "role": c.role,
                 "speaker_id": c.speaker_id, "speaker_name": c.speaker_name}
                for c in chars
            ],
        })

    # ─── OTP エンドポイント (Discord bot → Hono 検証用) ──────
    async def post_otp_verify(request: web.Request):
        """Hono からの OTP 検証リクエスト (127.0.0.1 のみ受付)"""
        from otp_store import verify
        body = await request.json()
        code = str(body.get("code", ""))
        ok   = verify(code)
        return web.json_response({"ok": ok})

    async def post_otp_generate(request: web.Request):
        """Discord bot からの OTP 生成リクエスト (127.0.0.1 のみ受付)"""
        from otp_store import generate
        code = generate()
        return web.json_response({"code": code})

    async def get_nim_usage(request: web.Request):
        """NIM日次使用状況を返す"""
        from services.llm import get_daily_usage
        from config import NIM_MIN_INTERVAL_SEC
        usage = get_daily_usage()
        return web.json_response({
            **usage,
            "remaining": max(0, usage["limit"] - usage["used"]),
            "min_interval_sec": NIM_MIN_INTERVAL_SEC,
        })

    app.router.add_get("/status",           get_status)
    app.router.add_get("/queue",            get_queue)
    app.router.add_get("/speakers",         get_speakers)
    app.router.add_get("/sse",              sse_status)
    app.router.add_get("/cast",             get_cast)
    app.router.add_get("/casts",            get_casts_list)
    app.router.add_get("/chars",            get_chars)
    app.router.add_get("/nim-usage",        get_nim_usage)
    app.router.add_get("/trending",         get_trending)
    app.router.add_get("/bgm-volume",       get_bgm_volume)
    app.router.add_post("/talk",            post_talk)
    app.router.add_post("/bgm",             post_bgm)
    app.router.add_post("/music",           post_music)
    app.router.add_post("/stop",            post_stop)
    app.router.add_post("/cast",            post_cast)
    app.router.add_post("/shuffle",         post_shuffle)
    app.router.add_post("/cast/custom",     post_cast_custom)
    app.router.add_post("/bgm-volume",      post_bgm_volume)
    app.router.add_post("/otp/verify",      post_otp_verify)
    app.router.add_post("/otp/generate",    post_otp_generate)

    return app

