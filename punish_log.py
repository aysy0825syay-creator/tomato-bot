"""
処罰ログ機能
- 処罰(警告・キック・BAN・タイムアウト・自動削除など)が行われたら、指定チャンネルに
  「対象者・罰・理由・実行者」を記録する
- 他のファイルからは log_punishment() を呼び出して使う
"""
import discord
from discord import app_commands
from discord.ext import commands

import config_manager as cfg

AUTO_EXECUTOR = "🤖 自動(VexaBot)"


def _short(text, limit: int = 1000) -> str:
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _person(obj) -> str:
    """ユーザー/メンバーは『名前 (ID)』の形に、それ以外はそのまま文字にする"""
    if isinstance(obj, (discord.Member, discord.User)):
        return f"{obj} (ID: {obj.id})"
    return str(obj)


async def log_punishment(guild: discord.Guild, target, punishment: str, reason: str, executor=None):
    """処罰ログを送信する。

    target     : 処罰された人(Member / User / 文字列)
    punishment : 罰の内容(例: "BAN", "タイムアウト(10分)", "メッセージ削除")
    reason     : 理由
    executor   : 実行した人。None のときは「自動」と表示する
    """
    channel_id = cfg.get_guild_config(guild.id)["punish_log_channel_id"]
    if not channel_id:
        return
    channel = guild.get_channel(channel_id)
    if channel is None:
        return

    embed = discord.Embed(title="🔨 処罰ログ", color=discord.Color.red(), timestamp=discord.utils.utcnow())
    embed.add_field(name="対象者", value=_short(_person(target)), inline=False)
    embed.add_field(name="罰", value=_short(punishment), inline=True)
    embed.add_field(name="理由", value=_short(reason), inline=True)
    embed.add_field(name="実行者", value=_short(_person(executor) if executor is not None else AUTO_EXECUTOR), inline=False)
    if isinstance(target, (discord.Member, discord.User)):
        embed.set_thumbnail(url=target.display_avatar.url)
    try:
        await channel.send(embed=embed)
    except Exception:
        pass


class PunishLogCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="punish_log_channel", description="処罰ログを送るチャンネルを設定します")
    @app_commands.describe(channel="処罰ログを送るチャンネル(スタッフ専用チャンネルがおすすめ)")
    @app_commands.checks.has_permissions(administrator=True)
    async def punish_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        cfg.update_guild_config(interaction.guild_id, punish_log_channel_id=channel.id)
        await interaction.response.send_message(
            f"📌 処罰ログの送信先を {channel.mention} に設定しました。\n"
            "警告・キック・BAN・タイムアウトや、自動対策による削除などが記録されます。",
            ephemeral=True,
        )

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "❌ このコマンドは「管理者」権限を持つメンバーのみ使用できます。"
        else:
            msg = f"❌ エラーが発生しました: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PunishLogCog(bot))
