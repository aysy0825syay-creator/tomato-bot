"""
サーバー統計機能
"""
import discord
from discord import app_commands
from discord.ext import commands


class StatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="server_stats", description="サーバーの統計情報を表示します")
    async def server_stats(self, interaction: discord.Interaction):
        guild = interaction.guild
        humans = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)
        online = sum(1 for m in guild.members if m.status != discord.Status.offline)
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)

        embed = discord.Embed(title=f"📊 {guild.name} の統計", color=discord.Color.blue())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="総メンバー数", value=str(guild.member_count), inline=True)
        embed.add_field(name="人間", value=str(humans), inline=True)
        embed.add_field(name="Bot", value=str(bots), inline=True)
        embed.add_field(name="オンライン", value=str(online), inline=True)
        embed.add_field(name="テキストチャンネル", value=str(text_channels), inline=True)
        embed.add_field(name="ボイスチャンネル", value=str(voice_channels), inline=True)
        embed.add_field(name="ロール数", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="サーバー作成日", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="ブースト数", value=str(guild.premium_subscription_count), inline=True)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))
