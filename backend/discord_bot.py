"""
Discord Bot: ボイスチャンネルへの接続・切断・再接続を管理
"""
import asyncio
import logging
import discord
from discord.ext import commands

from config import (
    DISCORD_TOKEN, DISCORD_GUILD_ID,
    DISCORD_VOICE_CHANNEL_ID, DISCORD_TEXT_CHANNEL_ID,
)

log = logging.getLogger("discord_bot")


class RadioBot(commands.Bot):
    def __init__(self, speech_queue, playback_queue, bgm_prefetch_q, status_queue):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)

        self.speech_queue   = speech_queue
        self.playback_queue = playback_queue
        self.bgm_prefetch_q = bgm_prefetch_q
        self.status_queue   = status_queue

        self.voice_client: discord.VoiceClient | None = None
        self._reconnect_task: asyncio.Task | None = None

    # ─── 起動 ─────────────────────────────────────────────
    async def start_bot(self):
        await self.start(DISCORD_TOKEN)

    async def on_ready(self):
        log.info(f"Discord接続完了: {self.user} (id={self.user.id})")
        await self._join_voice()

    # ─── ボイスチャンネル接続 ──────────────────────────────
    async def _join_voice(self):
        guild   = self.get_guild(DISCORD_GUILD_ID)
        channel = guild and guild.get_channel(DISCORD_VOICE_CHANNEL_ID)
        if not channel:
            log.error(f"ボイスチャンネル {DISCORD_VOICE_CHANNEL_ID} が見つかりません")
            return
        try:
            self.voice_client = await channel.connect(reconnect=True)
            log.info(f"ボイスチャンネル接続: {channel.name}")
            await self._push_status("connected", channel.name)
        except Exception as e:
            log.error(f"ボイスチャンネル接続失敗: {e}")
            await self._schedule_reconnect()

    async def _schedule_reconnect(self, delay: float = 30.0):
        await asyncio.sleep(delay)
        log.info("ボイスチャンネル再接続を試みます")
        await self._join_voice()

    # ─── 音声再生 ──────────────────────────────────────────
    def play_audio(self, source: discord.AudioSource, after_callback=None):
        if not self.voice_client or not self.voice_client.is_connected():
            log.warning("ボイスクライアントが未接続です")
            return
        if self.voice_client.is_playing():
            self.voice_client.stop()
        self.voice_client.play(source, after=after_callback)

    def is_playing(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_playing())

    def stop(self):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()

    # ─── ステータス通知 ────────────────────────────────────
    async def _push_status(self, event: str, detail: str = ""):
        try:
            self.status_queue.put_nowait({"event": event, "detail": detail})
        except asyncio.QueueFull:
            pass

    # ─── 切断イベント (自動再接続) ──────────────────────────
    async def on_voice_state_update(self, member, before, after):
        if member != self.user:
            return
        if before.channel and not after.channel:
            log.warning("ボイスチャンネルから切断されました。再接続します...")
            await self._schedule_reconnect(delay=5.0)
