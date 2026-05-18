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
        await self.bot.music_request_queue.put({"query": query, "title": query})
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send(f"🎵 「{query}」を音楽キューに追加しました", delete_after=5)

    @app_commands.command(name="music", description="音楽リクエストをキューに追加する")
    @app_commands.describe(query="曲名やアーティスト名")
    async def slash_music(self, interaction: discord.Interaction, query: str):
        await self.bot.music_request_queue.put({"query": query, "title": query})
        await interaction.response.send_message(f"🎵 「{query}」を音楽キューに追加しました", ephemeral=True)

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
    def __init__(self, speech_queue, playback_queue, bgm_prefetch_q, music_request_queue, status_queue):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)

        self.speech_queue        = speech_queue
        self.playback_queue      = playback_queue
        self.bgm_prefetch_q      = bgm_prefetch_q
        self.music_request_queue = music_request_queue
        self.status_queue        = status_queue

        self.voice_client: discord.VoiceClient | None = None

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

    # ─── 切断イベント (自動再接続) ──────────────────────────
    async def on_voice_state_update(self, member, before, after):
        if member != self.user:
            return
        if before.channel and not after.channel:
            log.warning("ボイスチャンネルから切断されました。再接続します...")
            asyncio.create_task(self._schedule_reconnect(delay=5.0))
