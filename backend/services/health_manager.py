"""
HealthManager: サブシステムの死活監視を集約し、全体ヘルス状態を算出する。

サブシステム:
  discord   - Bot接続状態
  voicevox  - GET /version → HTTP 200
  nim       - NIM API GET /models
  queue     - キューサイズが閾値以下か
  playback  - 最終再生から30分以内か
  storage   - ディスク使用率が95%未満か

スコアリング:
  6/6 healthy → UP
  5/6         → UP (msg: degraded)
  4/6         → UP (msg: degraded)
  ≤3/6        → DOWN
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("health_manager")

CHECK_TIMEOUT_SEC = 8.0   # 各ヘルスチェックのタイムアウト
PLAYBACK_STALE_SEC = 1800  # 再生が30分以上ない → unhealthy

# キューサイズ上限
QUEUE_TTS_MAX      = 50
QUEUE_PLAYBACK_MAX = 20

# ストレージ閾値
STORAGE_WARN_PCT     = 80.0
STORAGE_CRITICAL_PCT = 90.0
STORAGE_DOWN_PCT     = 95.0


@dataclass
class SubsystemHealth:
    ok: bool
    detail: str = ""


@dataclass
class HealthReport:
    discord:  SubsystemHealth = field(default_factory=lambda: SubsystemHealth(False))
    voicevox: SubsystemHealth = field(default_factory=lambda: SubsystemHealth(False))
    nim:      SubsystemHealth = field(default_factory=lambda: SubsystemHealth(False))
    queue:    SubsystemHealth = field(default_factory=lambda: SubsystemHealth(False))
    playback: SubsystemHealth = field(default_factory=lambda: SubsystemHealth(False))
    storage:  SubsystemHealth = field(default_factory=lambda: SubsystemHealth(False))
    timestamp: float = field(default_factory=time.time)

    def healthy_count(self) -> int:
        return sum(1 for s in self._subsystems() if s.ok)

    def overall_status(self) -> str:
        """'up' | 'down'"""
        return "up" if self.healthy_count() >= 4 else "down"

    def overall_msg(self) -> str:
        c = self.healthy_count()
        if c == 6:
            return "All systems OK"
        parts = [name for name, s in self._named() if not s.ok]
        label = ", ".join(parts)
        if c >= 4:
            return f"degraded: {label}"
        return f"DOWN: {label}"

    def to_dict(self) -> dict[str, Any]:
        import datetime
        ts = datetime.datetime.fromtimestamp(self.timestamp, tz=datetime.timezone.utc).isoformat()
        return {
            "status":    self.overall_status(),
            "score":     f"{self.healthy_count()}/6",
            "discord":   {"ok": self.discord.ok,  "detail": self.discord.detail},
            "voicevox":  {"ok": self.voicevox.ok, "detail": self.voicevox.detail},
            "nim":       {"ok": self.nim.ok,       "detail": self.nim.detail},
            "playback":  {"ok": self.playback.ok,  "detail": self.playback.detail},
            "queue":     {"ok": self.queue.ok,     "detail": self.queue.detail},
            "storage":   {"ok": self.storage.ok,   "detail": self.storage.detail},
            "timestamp": ts,
        }

    def push_msg(self) -> str:
        lines = []
        for name, s in self._named():
            lines.append(f"{name.upper()}: {'OK' if s.ok else 'NG - ' + s.detail}")
        return " | ".join(lines)

    def _subsystems(self):
        return [self.discord, self.voicevox, self.nim,
                self.queue, self.playback, self.storage]

    def _named(self):
        return [
            ("discord",  self.discord),
            ("voicevox", self.voicevox),
            ("nim",      self.nim),
            ("queue",    self.queue),
            ("playback", self.playback),
            ("storage",  self.storage),
        ]


class HealthManager:
    """全サブシステムのヘルスを並列収集するマネージャー。"""

    def __init__(self):
        # 外部コンポーネントは後から inject する
        self._bot           = None
        self._tts_queue     = None
        self._playback_queue = None
        self._playback_worker = None
        self._last_report: HealthReport | None = None

    def inject(self, *, bot=None, tts_queue=None, playback_queue=None, playback_worker=None):
        self._bot             = bot
        self._tts_queue       = tts_queue
        self._playback_queue  = playback_queue
        self._playback_worker = playback_worker

    async def collect(self) -> HealthReport:
        """全サブシステムをasyncio.gatherで並列チェック。"""
        results = await asyncio.gather(
            self._check_discord(),
            self._check_voicevox(),
            self._check_nim(),
            self._check_queue(),
            self._check_playback(),
            self._check_storage(),
            return_exceptions=True,
        )

        def _safe(r, name: str) -> SubsystemHealth:
            if isinstance(r, Exception):
                log.warning(f"HealthCheck [{name}] 例外: {r}")
                return SubsystemHealth(False, str(r)[:80])
            return r

        report = HealthReport(
            discord  = _safe(results[0], "discord"),
            voicevox = _safe(results[1], "voicevox"),
            nim      = _safe(results[2], "nim"),
            queue    = _safe(results[3], "queue"),
            playback = _safe(results[4], "playback"),
            storage  = _safe(results[5], "storage"),
        )
        self._last_report = report
        return report

    @property
    def last_report(self) -> HealthReport | None:
        return self._last_report

    # ──────────────────────────────────────────────────────────
    # 各サブシステムのチェック実装
    # ──────────────────────────────────────────────────────────

    async def _check_discord(self) -> SubsystemHealth:
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_SEC):
                if self._bot is None:
                    return SubsystemHealth(False, "bot未初期化")
                ready = self._bot.is_ready()
                return SubsystemHealth(ready, "" if ready else "bot not ready")
        except TimeoutError:
            return SubsystemHealth(False, "timeout")

    async def _check_voicevox(self) -> SubsystemHealth:
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_SEC):
                import aiohttp
                from config import VOICEVOX_URL
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(f"{VOICEVOX_URL}/version") as resp:
                        if resp.status == 200:
                            ver = (await resp.text()).strip().strip('"')
                            return SubsystemHealth(True, f"v{ver}")
                        return SubsystemHealth(False, f"HTTP {resp.status}")
        except TimeoutError:
            return SubsystemHealth(False, "timeout")
        except Exception as e:
            return SubsystemHealth(False, str(e)[:60])

    async def _check_nim(self) -> SubsystemHealth:
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_SEC):
                from config import LLM_API_BASE, LLM_API_KEY
                import aiohttp
                headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
                url = f"{LLM_API_BASE.rstrip('/')}/models"
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            return SubsystemHealth(True, "reachable")
                        return SubsystemHealth(False, f"HTTP {resp.status}")
        except TimeoutError:
            return SubsystemHealth(False, "timeout")
        except Exception as e:
            return SubsystemHealth(False, str(e)[:60])

    async def _check_queue(self) -> SubsystemHealth:
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_SEC):
                issues = []
                if self._tts_queue is not None:
                    sz = self._tts_queue.qsize()
                    if sz >= QUEUE_TTS_MAX:
                        issues.append(f"tts_queue={sz}")
                if self._playback_queue is not None:
                    sz = self._playback_queue.qsize()
                    if sz >= QUEUE_PLAYBACK_MAX:
                        issues.append(f"playback_queue={sz}")

                tts_sz = self._tts_queue.qsize() if self._tts_queue else 0
                pb_sz  = self._playback_queue.qsize() if self._playback_queue else 0
                detail = f"tts={tts_sz} playback={pb_sz}"
                return SubsystemHealth(len(issues) == 0, detail if not issues else ", ".join(issues))
        except TimeoutError:
            return SubsystemHealth(False, "timeout")

    async def _check_playback(self) -> SubsystemHealth:
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_SEC):
                pw = self._playback_worker
                if pw is None:
                    return SubsystemHealth(False, "worker未初期化")

                last_ts = getattr(pw, "_last_play_ts", None)
                if last_ts is None:
                    # まだ1度も再生していない（起動直後）→ OK扱い
                    return SubsystemHealth(True, "no playback yet")

                elapsed = time.time() - last_ts
                if elapsed < PLAYBACK_STALE_SEC:
                    mins = int(elapsed // 60)
                    return SubsystemHealth(True, f"last {mins}m ago")
                else:
                    mins = int(elapsed // 60)
                    return SubsystemHealth(False, f"stale {mins}m ago")
        except TimeoutError:
            return SubsystemHealth(False, "timeout")

    async def _check_storage(self) -> SubsystemHealth:
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_SEC):
                from config import DATA_DIR
                paths_to_check = [DATA_DIR, DATA_DIR.parent]
                worst_pct  = 0.0
                worst_path = ""
                for p in paths_to_check:
                    check_path = p
                    while not check_path.exists() and check_path != check_path.parent:
                        check_path = check_path.parent
                    if check_path.exists():
                        usage = shutil.disk_usage(check_path)
                        pct = usage.used / usage.total * 100
                        if pct > worst_pct:
                            worst_pct = pct
                            worst_path = str(check_path)

                if worst_pct == 0.0:
                    # フォールバック: root
                    usage = shutil.disk_usage("/")
                    worst_pct = usage.used / usage.total * 100
                    worst_path = "/"

                detail = f"{worst_pct:.1f}% ({worst_path})"
                ok = worst_pct < STORAGE_DOWN_PCT
                return SubsystemHealth(ok, detail)
        except TimeoutError:
            return SubsystemHealth(False, "timeout")
        except Exception as e:
            return SubsystemHealth(False, str(e)[:60])


# モジュールレベルシングルトン
health_manager = HealthManager()
