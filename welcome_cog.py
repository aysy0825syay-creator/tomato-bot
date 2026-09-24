"""
歓迎メッセージ & 自動ロール付与機能
"""
import discord
from discord import app_commands
from discord.ext import commands

import config_manager as cfg


class WelcomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_cfg = cfg.get_guild_config(member.guild.id)

        # 自動ロール付与
        if guild_cfg["autorole_id"]:
            role = member.guild.get_role(guild_cfg["autorole_id"])
            if role:
                try:
                    await member.add_roles(role, reason="自動ロール付与")
                except Exception:
                    pass

        # 歓迎メッセージ
        if guild_cfg["welcome_enabled"] and guild_cfg["welcome_channel_id"]:
            channel = member.guild.get_channel(guild_cfg["welcome_channel_id"])
            if channel:
                text = guild_cfg["welcome_message"].format(
                    user=member.mention, server=member.guild.name
                )
                embed = discord.Embed(description=text, color=discord.Color.orange())
                embed.set_thumbnail(url=member.display_avatar.url)
                if member.guild.icon:
                    embed.set_footer(text=member.guild.name, icon_url=member.guild.icon.url)
                await channel.send(embed=embed)

    # ───────── 設定コマンド ─────────
    @app_commands.command(name="welcome_toggle", description="歓迎メッセージの有効/無効を切り替えます")
    @app_commands.describe(enabled="有効にするならTrue、無効にするならFalse")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_toggle(self, interaction: discord.Interaction, enabled: bool):
        cfg.update_guild_config(interaction.guild_id, welcome_enabled=enabled)
        status = "有効" if enabled else "無効"
        await interaction.response.send_message(f"👋 歓迎メッセージを **{status}** にしました。", ephemeral=True)

    @app_commands.command(name="welcome_channel", description="歓迎メッセージを送るチャンネルを設定します")
    @app_commands.describe(channel="送信するチャンネル")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        cfg.update_guild_config(interaction.guild_id, welcome_channel_id=channel.id)
        await interaction.response.send_message(f"📌 歓迎メッセージのチャンネルを {channel.mention} に設定しました。", ephemeral=True)

    @app_commands.command(name="welcome_message", description="歓迎メッセージの文面を設定します({user}=メンション, {server}=サーバー名)")
    @app_commands.describe(text="メッセージ本文")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_message(self, interaction: discord.Interaction, text: str):
        cfg.update_guild_config(interaction.guild_id, welcome_message=text)
        await interaction.response.send_message("✏️ 歓迎メッセージを更新しました。", ephemeral=True)

    @app_commands.command(name="autorole", description="入室時に自動で付与するロールを設定します")
    @app_commands.describe(role="自動付与するロール(未指定で解除)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def autorole(self, interaction: discord.Interaction, role: discord.Role = None):
        cfg.update_guild_config(interaction.guild_id, autorole_id=role.id if role else None)
        if role:
            await interaction.response.send_message(f"🎭 自動付与ロールを {role.mention} に設定しました。", ephemeral=True)
        else:
            await interaction.response.send_message("🎭 自動ロール付与を解除しました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))
