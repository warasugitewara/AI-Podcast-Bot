"""
Uptime Kuma Push Monitor ワーカー。
60秒ごとにヘルスチェックを実行し、Push URLへGETリクエストを送る。
UPTIME_KUMA_PUSH_URL が空の場合はチェックのみ行い、Push はスキップする。
"""
from __future__ import annotations

import asyncio
import logging
import time

log = logging.getLogger("uptime_worker")

PUSH_INTERVAL_SEC = 60


async def uptime_worker(health_mgr) -> None:
    """health_mgr: HealthManager インスタンス"""
    from config import UPTIME_KUMA_PUSH_URL

    if not UPTIME_KUMA_PUSH_URL:
        log.info("UPTIME_KUMA_PUSH_URL 未設定のため Push をスキップ（ヘルスチェックは継続）")

    while True:
        try:
            report = await health_mgr.collect()
            status = report.overall_status()
            msg    = report.overall_msg()
            score  = report.healthy_count()
            log.info(f"[health] {status.upper()} {score}/6 — {msg}")

            if UPTIME_KUMA_PUSH_URL:
                await _push(UPTIME_KUMA_PUSH_URL, status, msg)

        except Exception as e:
            log.error(f"uptime_worker エラー: {e}", exc_info=True)

        await asyncio.sleep(PUSH_INTERVAL_SEC)


async def _push(url: str, status: str, msg: str) -> None:
    import aiohttp
    t0 = time.time()
    params = {
        "status": status,
        "msg":    msg[:200],  # URLパラメータ長制限
        "ping":   "",
    }
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                ping_ms = int((time.time() - t0) * 1000)
                params["ping"] = str(ping_ms)
                if resp.status == 200:
                    log.info(f"Uptime Kuma push OK ({status}, {ping_ms}ms)")
                else:
                    log.warning(f"Uptime Kuma push HTTP {resp.status}")
    except Exception as e:
        log.warning(f"Uptime Kuma push 失敗: {e}")
