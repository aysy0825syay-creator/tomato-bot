"""
メッセージ編集・削除ログ機能
- 荒らし対策として、誰が何を編集・削除したかを記録する
"""
import discord
from discord import app_commands
from discord.ext import commands

import config_manager as cfg


class LoggingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        guild_cfg = cfg.get_guild_config(message.guild.id)
        if not guild_cfg["modlog_enabled"] or not guild_cfg["modlog_channel_id"]:
            return
        channel = message.guild.get_channel(guild_cfg["modlog_channel_id"])
        if channel is None:
            return
        embed = discord.Embed(
            title="🗑️ メッセージ削除",
            description=message.content or "(内容なし・添付ファイルなど)",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="送信者", value=str(message.author))
        embed.add_field(name="チャンネル", value=message.channel.mention)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or before.guild is None or before.content == after.content:
            return
        guild_cfg = cfg.get_guild_config(before.guild.id)
        if not guild_cfg["modlog_enabled"] or not guild_cfg["modlog_channel_id"]:
            return
        channel = before.guild.get_channel(guild_cfg["modlog_channel_id"])
        if channel is None:
            return
        embed = discord.Embed(title="✏️ メッセージ編集", color=discord.Color.gold(), timestamp=discord.utils.utcnow())
        embed.add_field(name="送信者", value=str(before.author), inline=False)
        embed.add_field(name="編集前", value=(before.content or "(なし)")[:1000], inline=False)
        embed.add_field(name="編集後", value=(after.content or "(なし)")[:1000], inline=False)
        embed.add_field(name="チャンネル", value=before.channel.mention, inline=False)
        await channel.send(embed=embed)

    # ───────── 設定コマンド ─────────
    @app_commands.command(name="modlog_channel", description="編集・削除ログを送るチャンネルを設定します")
    @app_commands.describe(channel="ログを送るチャンネル")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def modlog_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        cfg.update_guild_config(interaction.guild_id, modlog_channel_id=channel.id)
        await interaction.response.send_message(f"📌 編集・削除ログのチャンネルを {channel.mention} に設定しました。", ephemeral=True)

    @app_commands.command(name="modlog_toggle", description="編集・削除ログの有効/無効を切り替えます")
    @app_commands.describe(enabled="有効にするならTrue、無効にするならFalse")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def modlog_toggle(self, interaction: discord.Interaction, enabled: bool):
        cfg.update_guild_config(interaction.guild_id, modlog_enabled=enabled)
        status = "有効" if enabled else "無効"
        await interaction.response.send_message(f"📝 編集・削除ログを **{status}** にしました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingCog(bot))
