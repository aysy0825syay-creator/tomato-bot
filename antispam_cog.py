"""
スパムフィルター機能
- 同じ内容の連投、招待リンクの連続投稿を検知して自動削除+一時タイムアウト
"""
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

import config_manager as cfg

SPAM_WINDOW_SECONDS = 8       # この秒数以内に…
SPAM_REPEAT_THRESHOLD = 4     # 同じ内容を何回送ったらスパム判定するか
TIMEOUT_MINUTES = 5           # 検知時のタイムアウト時間


class AntiSpamCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # (guild_id, user_id) -> 最近送ったメッセージの履歴
        self.recent: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=10))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        guild_cfg = cfg.get_guild_config(message.guild.id)
        if not guild_cfg["antispam_enabled"]:
            return

        key = (message.guild.id, message.author.id)
        now = time.time()
        history = self.recent[key]
        history.append((now, message.content))

        # 直近SPAM_WINDOW_SECONDS秒以内で、同じ内容が閾値回数以上あるか判定
        recent_same = [
            t for t, c in history
            if now - t <= SPAM_WINDOW_SECONDS and c == message.content
        ]

        invite_count = message.content.count("discord.gg/")

        is_spam = len(recent_same) >= SPAM_REPEAT_THRESHOLD or invite_count >= 3

        if is_spam:
            try:
                await message.delete()
            except Exception:
                pass
            try:
                until = discord.utils.utcnow() + timedelta(minutes=TIMEOUT_MINUTES)
                await message.author.timeout(until, reason="スパム自動検知")
            except Exception:
                pass
            try:
                warn_msg = await message.channel.send(
                    f"🚫 {message.author.mention} のスパム行為を検知したため、"
                    f"{TIMEOUT_MINUTES}分間タイムアウトしました。"
                )
                await warn_msg.delete(delay=8)
            except Exception:
                pass
            history.clear()

    # ───────── 設定コマンド ─────────
    @app_commands.command(name="antispam_toggle", description="スパムフィルターの有効/無効を切り替えます")
    @app_commands.describe(enabled="有効にするならTrue、無効にするならFalse")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def antispam_toggle(self, interaction: discord.Interaction, enabled: bool):
        cfg.update_guild_config(interaction.guild_id, antispam_enabled=enabled)
        status = "有効" if enabled else "無効"
        await interaction.response.send_message(f"🛡️ スパムフィルターを **{status}** にしました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiSpamCog(bot))
