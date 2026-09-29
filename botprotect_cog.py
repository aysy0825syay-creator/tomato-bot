"""
Bot荒らし対策
- Botスパム対策: 他のBotが短時間に連投したらメッセージを削除
- Botリンク対策: 他のBotがリンクを含むメッセージを送ったら削除
- どちらも「ホワイトリストに入れたBot」と「除外チャンネル」は対象外にできる
"""
import re
import time
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands

import config_manager as cfg
from punish_log import log_punishment

URL_PATTERN = re.compile(r"https?://\S+")
WINDOW_SECONDS = 8  # この秒数以内の連投をスパムとみなす


class BotProtectCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # (guild_id, bot_id) -> 直近の送信時刻
        self.recent_bot_messages: dict[tuple, deque] = defaultdict(deque)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or not message.author.bot:
            return
        if message.author.id == self.bot.user.id:
            return  # 自分自身は対象外

        guild_cfg = cfg.get_guild_config(message.guild.id)
        whitelist = guild_cfg["botlink_whitelist"]
        if message.author.id in whitelist:
            return

        handled = await self._check_botspam(message, guild_cfg)
        if not handled:
            await self._check_botlink(message, guild_cfg)

    # ───────── Botスパム対策 ─────────
    async def _check_botspam(self, message: discord.Message, guild_cfg: dict) -> bool:
        if not guild_cfg["botspam_enabled"]:
            return False
        if message.channel.id in guild_cfg["botspam_excluded_channels"]:
            return False

        key = (message.guild.id, message.author.id)
        now = time.time()
        history = self.recent_bot_messages[key]
        history.append(now)
        while history and now - history[0] > WINDOW_SECONDS:
            history.popleft()

        if len(history) < guild_cfg["botspam_limit"]:
            return False

        history.clear()
        deleted = 0
        try:
            async for msg in message.channel.history(limit=50):
                if msg.author.id == message.author.id and (now - msg.created_at.timestamp()) <= WINDOW_SECONDS + 5:
                    try:
                        await msg.delete()
                        deleted += 1
                    except Exception:
                        pass
        except Exception:
            pass

        await log_punishment(
            message.guild, message.author, "メッセージ削除(連投)",
            f"{WINDOW_SECONDS}秒以内に{guild_cfg['botspam_limit']}件以上送信({deleted}件削除)",
        )
        return True

    # ───────── Botリンク対策 ─────────
    async def _check_botlink(self, message: discord.Message, guild_cfg: dict):
        if not guild_cfg["botlink_enabled"]:
            return
        if message.channel.id in guild_cfg["botlink_excluded_channels"]:
            return
        if not URL_PATTERN.search(message.content):
            return

        try:
            await message.delete()
        except Exception:
            return

        await log_punishment(
            message.guild, message.author, "メッセージ削除(Botリンク)",
            "許可されていないBotがリンクを含むメッセージを送信",
        )

    # ───────── 設定コマンド:Botスパム ─────────
    @app_commands.command(name="botspam_toggle", description="Botスパム対策の有効/無効を切り替えます")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def botspam_toggle(self, interaction: discord.Interaction, enabled: bool):
        cfg.update_guild_config(interaction.guild_id, botspam_enabled=enabled)
        await interaction.response.send_message(f"🤖 Botスパム対策を **{'有効' if enabled else '無効'}** にしました。", ephemeral=True)

    @app_commands.command(name="botspam_limit", description=f"{WINDOW_SECONDS}秒以内に何通でBotスパムとみなすか設定します")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def botspam_limit(self, interaction: discord.Interaction, count: int):
        count = max(2, min(count, 50))
        cfg.update_guild_config(interaction.guild_id, botspam_limit=count)
        await interaction.response.send_message(f"🤖 Botスパムの基準を「{WINDOW_SECONDS}秒に{count}通」にしました。", ephemeral=True)

    @app_commands.command(name="botspam_exclude_channel", description="Botスパム対策の除外チャンネルを追加/削除します")
    @app_commands.describe(channel="対象のチャンネル", action="追加するか削除するか")
    @app_commands.choices(action=[
        app_commands.Choice(name="追加", value="add"),
        app_commands.Choice(name="削除", value="remove"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def botspam_exclude_channel(self, interaction: discord.Interaction, channel: discord.TextChannel, action: app_commands.Choice[str]):
        c = cfg.get_guild_config(interaction.guild_id)
        excluded = c["botspam_excluded_channels"]
        if action.value == "add" and channel.id not in excluded:
            excluded.append(channel.id)
        elif action.value == "remove" and channel.id in excluded:
            excluded.remove(channel.id)
        cfg.update_guild_config(interaction.guild_id, botspam_excluded_channels=excluded)
        await interaction.response.send_message(f"✅ {channel.mention} をBotスパム対策の除外リストから{'追加' if action.value == 'add' else '削除'}しました。", ephemeral=True)

    # ───────── 設定コマンド:Botリンク ─────────
    @app_commands.command(name="botlink_toggle", description="Botから送られるリンクの対策を切り替えます")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def botlink_toggle(self, interaction: discord.Interaction, enabled: bool):
        cfg.update_guild_config(interaction.guild_id, botlink_enabled=enabled)
        await interaction.response.send_message(f"🔗 Botリンク対策を **{'有効' if enabled else '無効'}** にしました。", ephemeral=True)

    @app_commands.command(name="botlink_exclude_channel", description="Botリンク対策の除外チャンネルを追加/削除します")
    @app_commands.describe(channel="対象のチャンネル", action="追加するか削除するか")
    @app_commands.choices(action=[
        app_commands.Choice(name="追加", value="add"),
        app_commands.Choice(name="削除", value="remove"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def botlink_exclude_channel(self, interaction: discord.Interaction, channel: discord.TextChannel, action: app_commands.Choice[str]):
        c = cfg.get_guild_config(interaction.guild_id)
        excluded = c["botlink_excluded_channels"]
        if action.value == "add" and channel.id not in excluded:
            excluded.append(channel.id)
        elif action.value == "remove" and channel.id in excluded:
            excluded.remove(channel.id)
        cfg.update_guild_config(interaction.guild_id, botlink_excluded_channels=excluded)
        await interaction.response.send_message(f"✅ {channel.mention} をBotリンク対策の除外リストから{'追加' if action.value == 'add' else '削除'}しました。", ephemeral=True)

    # ───────── ホワイトリストBot ─────────
    @app_commands.command(name="botlink_whitelist_add", description="Botスパム/Botリンク対策の対象外にするBotを追加します")
    @app_commands.describe(bot_user="対象外にするBot")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def botlink_whitelist_add(self, interaction: discord.Interaction, bot_user: discord.Member):
        if not bot_user.bot:
            await interaction.response.send_message("⚠️ Botアカウントを指定してください。", ephemeral=True)
            return
        c = cfg.get_guild_config(interaction.guild_id)
        whitelist = c["botlink_whitelist"]
        if bot_user.id not in whitelist:
            whitelist.append(bot_user.id)
            cfg.update_guild_config(interaction.guild_id, botlink_whitelist=whitelist)
        await interaction.response.send_message(f"✅ {bot_user.mention} をホワイトリストに追加しました。", ephemeral=True)

    @app_commands.command(name="botlink_whitelist_remove", description="ホワイトリストからBotを削除します")
    @app_commands.describe(bot_user="削除するBot")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def botlink_whitelist_remove(self, interaction: discord.Interaction, bot_user: discord.Member):
        c = cfg.get_guild_config(interaction.guild_id)
        whitelist = c["botlink_whitelist"]
        if bot_user.id in whitelist:
            whitelist.remove(bot_user.id)
            cfg.update_guild_config(interaction.guild_id, botlink_whitelist=whitelist)
            await interaction.response.send_message(f"➖ {bot_user.mention} をホワイトリストから削除しました。", ephemeral=True)
        else:
            await interaction.response.send_message("そのBotはホワイトリストに登録されていません。", ephemeral=True)

    @app_commands.command(name="botlink_whitelist_list", description="ホワイトリストのBot一覧を表示します")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def botlink_whitelist_list(self, interaction: discord.Interaction):
        whitelist = cfg.get_guild_config(interaction.guild_id)["botlink_whitelist"]
        if not whitelist:
            await interaction.response.send_message("ホワイトリストは空です。", ephemeral=True)
            return
        lines = []
        for bot_id in whitelist:
            member = interaction.guild.get_member(bot_id)
            lines.append(f"・{member.mention if member else f'ID: {bot_id}'}")
        await interaction.response.send_message("🤖 ホワイトリストBot一覧\n" + "\n".join(lines), ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "❌ このコマンドは「サーバー管理」権限を持つメンバーのみ使用できます。"
        else:
            msg = f"❌ エラーが発生しました: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(BotProtectCog(bot))
