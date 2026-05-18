"""
Discord Bot: ボイスチャンネルへの接続・切断・再接続を管理
プレフィックスコマンド (!otp, !start 等) とスラッシュコマンド (/otp, /start 等) を実装。
"""
import asyncio
import logging
import discord
from discord.ext import commands
from discord import app_commands

from config import (
    DISCORD_TOKEN, DISCORD_GUILD_ID,
    DISCORD_VOICE_CHANNEL_ID,
    VC_EMPTY_TIMEOUT_SEC,
)

log = logging.getLogger("discord_bot")


# ─── コマンド定義 (Cogとして登録) ──────────────────────────────
class PodcastCog(commands.Cog):
    def __init__(self, bot: "RadioBot"):
        self.bot = bot

    # ─── OTP ─────────────────────────────────────────────────
    @commands.command(name="otp")
    async def cmd_otp(self, ctx: commands.Context):
        """Web UI へのアクセス用 OTP を DM で送信する"""
        await self._send_otp(ctx.author)
        try:
            await ctx.message.delete()
        except Exception:
            pass

    @app_commands.command(name="otp", description="Web UIアクセス用OTPをDMで送信")
    async def slash_otp(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self._send_otp(interaction.user)
        await interaction.followup.send("✅ OTPをDMに送りました", ephemeral=True)

    async def _send_otp(self, user: discord.User):
        import aiohttp
        from config import BACKEND_API_PORT
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"http://127.0.0.1:{BACKEND_API_PORT}/otp/generate"
                ) as resp:
                    data = await resp.json()
            code = data["code"]
            await user.send(
                f"🔐 **AI Podcast Bot Web UI アクセスコード**\n"
                f"```{code}```\n"
                f"⏱ 有効期限: **10分** / 1回限り有効\n"
                f"Web UI のログインページで入力してください。"
            )
        except Exception as e:
            log.error(f"OTP生成失敗: {e}")
            await user.send("⚠️ OTPの生成に失敗しました。バックエンドが起動しているか確認してください。")

    # ─── START ───────────────────────────────────────────────
    @commands.command(name="start")
    async def cmd_start(self, ctx: commands.Context):
        """放送を即座に開始する"""
        await self.bot.speech_queue.put({"topic": ""})
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send("▶ 放送を開始します", delete_after=5)

    @app_commands.command(name="start", description="放送を開始する")
    async def slash_start(self, interaction: discord.Interaction):
        await self.bot.speech_queue.put({"topic": ""})
        await interaction.response.send_message("▶ 放送を開始します", ephemeral=True)

    # ─── STOP ────────────────────────────────────────────────
    @commands.command(name="stop")
    async def cmd_stop(self, ctx: commands.Context):
        """現在の再生を停止する"""
        self.bot.stop()
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send("⏹ 停止しました", delete_after=5)

    @app_commands.command(name="stop", description="現在の再生を停止する")
    async def slash_stop(self, interaction: discord.Interaction):
        self.bot.stop()
        await interaction.response.send_message("⏹ 停止しました", ephemeral=True)

    # ─── TOPIC ───────────────────────────────────────────────
    @commands.command(name="topic")
    async def cmd_topic(self, ctx: commands.Context, *, topic: str):
        """指定したトピックでトークを生成する  例: !topic 宇宙開発の最新ニュース"""
        await self.bot.speech_queue.put({"topic": topic})
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send(f"📝 トピック「{topic}」を予約しました", delete_after=5)

    @app_commands.command(name="topic", description="指定したトピックでトークを生成する")
    @app_commands.describe(topic="話してほしいトピック")
    async def slash_topic(self, interaction: discord.Interaction, topic: str):
        await self.bot.speech_queue.put({"topic": topic})
        await interaction.response.send_message(f"📝 トピック「{topic}」を予約しました", ephemeral=True)

    # ─── MUSIC ───────────────────────────────────────────────
    @commands.command(name="music")
    async def cmd_music(self, ctx: commands.Context, *, query: str):
        """音楽リクエストをキューに追加する  例: !music lofi hip hop"""
        await self.bot.music_request_queue.put({"query": query, "title": query, "user_request": True})
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send(f"🎵 「{query}」を音楽キューに追加しました", delete_after=5)

    @app_commands.command(name="music", description="音楽リクエストをキューに追加する")
    @app_commands.describe(query="曲名やアーティスト名")
    async def slash_music(self, interaction: discord.Interaction, query: str):
        await self.bot.music_request_queue.put({"query": query, "title": query, "user_request": True})
        await interaction.response.send_message(f"🎵 「{query}」を音楽キューに追加しました", ephemeral=True)

    # ─── VOLUME ──────────────────────────────────────────────
    @commands.command(name="volume")
    async def cmd_volume(self, ctx: commands.Context, value: str = ""):
        """BGM音量を変更する (0〜200、省略で現在値表示)  例: !volume 80"""
        pw = self.bot.playback_worker
        if pw is None:
            await ctx.send("⚠️ PlaybackWorkerが未初期化です", delete_after=5)
            return
        if not value:
            await ctx.send(f"🔊 BGM音量: **{pw.bgm_volume:.0%}**", delete_after=10)
            return
        try:
            vol = float(value.replace("%", "")) / 100.0
            vol = max(0.0, min(2.0, vol))
        except ValueError:
            await ctx.send("⚠️ 数値を入力してください (例: !volume 80)", delete_after=5)
            return
        pw.bgm_volume = vol
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send(f"🔊 BGM音量を **{vol:.0%}** に変更しました", delete_after=5)

    @app_commands.command(name="volume", description="BGM音量を変更する (0〜200%、省略で現在値表示)")
    @app_commands.describe(value="音量 (0〜200、省略で現在値表示)")
    async def slash_volume(self, interaction: discord.Interaction, value: int = -1):
        pw = self.bot.playback_worker
        if pw is None:
            await interaction.response.send_message("⚠️ PlaybackWorkerが未初期化です", ephemeral=True)
            return
        if value < 0:
            await interaction.response.send_message(f"🔊 BGM音量: **{pw.bgm_volume:.0%}**", ephemeral=True)
            return
        vol = max(0.0, min(2.0, value / 100.0))
        pw.bgm_volume = vol
        await interaction.response.send_message(f"🔊 BGM音量を **{vol:.0%}** に変更しました", ephemeral=True)

    # ─── CAST ────────────────────────────────────────────────
    @commands.command(name="cast")
    async def cmd_cast(self, ctx: commands.Context, name: str = ""):
        """キャストを変更する（引数なしで現在のキャストを表示）"""
        from services.character_manager import character_manager
        if not name:
            await ctx.send(character_manager.status_embed(), delete_after=15)
            return
        result = character_manager.set_cast(name)
        if result is None:
            await ctx.send(f"⚠️ キャスト「{name}」は存在しません", delete_after=5)
        else:
            try:
                await ctx.message.delete()
            except Exception:
                pass
            await ctx.send(f"🎭 キャスト変更: **{result['label']}**", delete_after=5)

    @app_commands.command(name="cast", description="キャストを変更する（引数なしで現在のキャストを表示）")
    @app_commands.describe(cast_name="キャスト名（省略で現在のキャスト表示）")
    async def slash_cast(self, interaction: discord.Interaction, cast_name: str = ""):
        from services.character_manager import character_manager
        if not cast_name:
            await interaction.response.send_message(character_manager.status_embed(), ephemeral=True)
            return
        result = character_manager.set_cast(cast_name)
        if result is None:
            await interaction.response.send_message(f"⚠️ キャスト「{cast_name}」は存在しません", ephemeral=True)
        else:
            await interaction.response.send_message(f"🎭 キャスト変更: **{result['label']}**", ephemeral=True)

    # ─── CASTS ───────────────────────────────────────────────
    @commands.command(name="casts")
    async def cmd_casts(self, ctx: commands.Context):
        """利用可能なキャスト一覧を表示する"""
        from services.character_manager import character_manager
        await ctx.send(character_manager.list_casts_text(), delete_after=20)

    @app_commands.command(name="casts", description="利用可能なキャスト一覧を表示する")
    async def slash_casts(self, interaction: discord.Interaction):
        from services.character_manager import character_manager
        await interaction.response.send_message(character_manager.list_casts_text(), ephemeral=True)

    # ─── CHARS ───────────────────────────────────────────────
    @commands.command(name="chars")
    async def cmd_chars(self, ctx: commands.Context):
        """キャラクター一覧を表示する"""
        from services.character_manager import character_manager
        await ctx.send(character_manager.list_chars_text(), delete_after=20)

    @app_commands.command(name="chars", description="キャラクター一覧を表示する")
    async def slash_chars(self, interaction: discord.Interaction):
        from services.character_manager import character_manager
        await interaction.response.send_message(character_manager.list_chars_text(), ephemeral=True)

    # ─── SHUFFLE ─────────────────────────────────────────────
    @commands.command(name="shuffle")
    async def cmd_shuffle(self, ctx: commands.Context):
        """ランダムにキャストを変更する"""
        from services.character_manager import character_manager
        result = character_manager.shuffle()
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send(f"🎲 キャストをシャッフル: **{result['label']}**", delete_after=5)

    @app_commands.command(name="shuffle", description="ランダムにキャストを変更する")
    async def slash_shuffle(self, interaction: discord.Interaction):
        from services.character_manager import character_manager
        result = character_manager.shuffle()
        await interaction.response.send_message(f"🎲 キャストをシャッフル: **{result['label']}**", ephemeral=True)


# ─── Bot 本体 ──────────────────────────────────────────────────
class RadioBot(commands.Bot):
    def __init__(self, speech_queue, playback_queue, bgm_prefetch_q, music_request_queue, status_queue,
                 broadcast_active: asyncio.Event):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)

        self.speech_queue        = speech_queue
        self.playback_queue      = playback_queue
        self.bgm_prefetch_q      = bgm_prefetch_q
        self.music_request_queue = music_request_queue
        self.status_queue        = status_queue
        self.broadcast_active    = broadcast_active  # Set=放送中, Cleared=一時停止

        self.voice_client: discord.VoiceClient | None = None
        self._empty_timer: asyncio.Task | None = None  # VC空室タイマー
        self.playback_worker = None  # main.py から後から設定される

    async def setup_hook(self):
        """CogとスラッシュコマンドをGuildに同期"""
        await self.add_cog(PodcastCog(self))
        guild = discord.Object(id=DISCORD_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        log.info(f"スラッシュコマンドをGuild {DISCORD_GUILD_ID} に同期しました")

    # ─── 起動 ──────────────────────────────────────────────
    async def start_bot(self):
        await self.start(DISCORD_TOKEN)

    async def on_ready(self):
        log.info(f"Discord接続完了: {self.user} (id={self.user.id})")
        await self._join_voice()

    # ─── ボイスチャンネル接続 ───────────────────────────────
    async def _join_voice(self):
        guild   = self.get_guild(DISCORD_GUILD_ID)
        channel = guild and guild.get_channel(DISCORD_VOICE_CHANNEL_ID)
        if not channel:
            log.error(f"ボイスチャンネル {DISCORD_VOICE_CHANNEL_ID} が見つかりません")
            return
        try:
            self.voice_client = await channel.connect(reconnect=True, self_deaf=True)
            log.info(f"ボイスチャンネル接続: {channel.name}")
            await self._push_status("connected", channel.name)
        except Exception as e:
            log.error(f"ボイスチャンネル接続失敗: {e}")
            asyncio.create_task(self._schedule_reconnect())

    async def _schedule_reconnect(self, delay: float = 30.0):
        await asyncio.sleep(delay)
        log.info("ボイスチャンネル再接続を試みます")
        await self._join_voice()

    # ─── 音声再生 ───────────────────────────────────────────
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

    # ─── ステータス通知 ─────────────────────────────────────
    async def _push_status(self, event: str, detail: str = ""):
        try:
            self.status_queue.put_nowait({"event": event, "detail": detail})
        except asyncio.QueueFull:
            pass

    # ─── 切断イベント (自動再接続 + VC空室検知) ────────────
    async def on_voice_state_update(self, member: discord.Member, before, after):
        # ── Bot自身の切断 → 再接続 ──────────────────────────
        if member == self.user:
            if before.channel and not after.channel:
                log.warning("ボイスチャンネルから切断されました。再接続します...")
                asyncio.create_task(self._schedule_reconnect(delay=5.0))
            return

        # ── 人間の入退室 → VC空室タイマー管理 ───────────────
        if VC_EMPTY_TIMEOUT_SEC <= 0:
            return  # 機能無効

        guild   = self.get_guild(DISCORD_GUILD_ID)
        channel = guild and guild.get_channel(DISCORD_VOICE_CHANNEL_ID)
        if not channel:
            return

        human_count = sum(1 for m in channel.members if not m.bot)

        if human_count == 0:
            # 全員退室 → タイマー開始（重複防止）
            if self._empty_timer is None or self._empty_timer.done():
                log.info(f"VC空室検知。{VC_EMPTY_TIMEOUT_SEC}秒後に放送を一時停止します")
                await self._push_status("vc_empty", f"{VC_EMPTY_TIMEOUT_SEC}秒後に停止")
                self._empty_timer = asyncio.create_task(self._empty_timeout())
        else:
            # 誰かが入室 → タイマーキャンセル
            if self._empty_timer and not self._empty_timer.done():
                self._empty_timer.cancel()
                self._empty_timer = None
                log.info(f"VC復帰 ({human_count}人)。タイマーキャンセル")

            # 停止中だった場合は放送再開を案内
            if not self.broadcast_active.is_set():
                self.broadcast_active.set()
                log.info("放送アクティブ状態に復帰")
                await self._notify_vc(
                    f"👋 {member.display_name} さんが入室しました。\n"
                    f"▶ `/start` で放送を再開できます。"
                )

    async def _empty_timeout(self):
        """VC空室タイムアウト処理"""
        try:
            await asyncio.sleep(VC_EMPTY_TIMEOUT_SEC)
            log.info("VC空室タイムアウト。放送を一時停止します")
            self.stop()                      # 現在の再生を停止
            self.broadcast_active.clear()    # ContentScheduler の新規生成を停止
            await self._push_status("paused_empty_vc", "VC空室のため停止")
            await self._notify_vc(
                "⏸ ボイスチャンネルが空になったため放送を一時停止しました。\n"
                "入室後 `/start` で再開できます。"
            )
        except asyncio.CancelledError:
            pass  # 誰かが戻ってきた

    async def _notify_vc(self, message: str):
        """VCのテキストチャット (同一チャンネルID) にメッセージを送信"""
        try:
            guild   = self.get_guild(DISCORD_GUILD_ID)
            channel = guild and guild.get_channel(DISCORD_VOICE_CHANNEL_ID)
            if channel and hasattr(channel, "send"):
                await channel.send(message)
        except Exception as e:
            log.warning(f"VC通知失敗: {e}")
