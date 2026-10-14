"""
サーバー初期設定(ワンコマンドセットアップ)機能
- スタッフロール、必要なカテゴリ・チャンネル、閲覧/発言権限をまとめて自動作成する
- 作成後、処罰ログ・歓迎メッセージ・チケットのスタッフロールなど、ボット側の設定にも自動反映する
- 既に同名のロール/カテゴリ/チャンネルがある場合は、重複して作らずそのまま再利用する
"""
import asyncio

import discord
from discord import app_commands
from discord.ext import commands

import config_manager as cfg
from punish_log import log_punishment

STAFF_ROLE_NAME = "スタッフ"


class SetupConfirmView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("⚠️ コマンドを実行した本人のみ操作できます。", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="実行する", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        await interaction.response.edit_message(content="⚙️ セットアップを開始します…", view=None)

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        await interaction.response.edit_message(content="❌ キャンセルしました。", view=None)


class SetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_or_create_role(self, guild: discord.Guild, name: str, **kwargs) -> discord.Role:
        role = discord.utils.get(guild.roles, name=name)
        if role:
            return role
        role = await guild.create_role(name=name, reason="サーバー初期設定", **kwargs)
        await asyncio.sleep(0.3)
        return role

    async def get_or_create_category(self, guild: discord.Guild, name: str, overwrites=None) -> discord.CategoryChannel:
        category = discord.utils.get(guild.categories, name=name)
        if category:
            return category
        category = await guild.create_category(name, overwrites=overwrites or {}, reason="サーバー初期設定")
        await asyncio.sleep(0.3)
        return category

    async def get_or_create_text(self, guild: discord.Guild, name: str, category, overwrites=None) -> discord.TextChannel:
        existing = discord.utils.get(guild.text_channels, name=name, category=category)
        if existing:
            return existing
        ch = await guild.create_text_channel(name, category=category, overwrites=overwrites or {}, reason="サーバー初期設定")
        await asyncio.sleep(0.3)
        return ch

    async def get_or_create_voice(self, guild: discord.Guild, name: str, category, overwrites=None) -> discord.VoiceChannel:
        existing = discord.utils.get(guild.voice_channels, name=name, category=category)
        if existing:
            return existing
        ch = await guild.create_voice_channel(name, category=category, overwrites=overwrites or {}, reason="サーバー初期設定")
        await asyncio.sleep(0.3)
        return ch

    @app_commands.command(name="server_setup", description="必要なロール・カテゴリ・チャンネル・権限をまとめて自動作成します")
    @app_commands.checks.has_permissions(administrator=True)
    async def server_setup(self, interaction: discord.Interaction):
        view = SetupConfirmView(interaction.user.id)
        await interaction.response.send_message(
            "⚙️ **サーバーの初期セットアップを実行しますか?**\n"
            "以下を自動作成します(同名のものが既にあれば、それをそのまま使います)。\n"
            "・「スタッフ」ロール\n"
            "・インフォメーション/コミュニティ/スタッフ専用/ボイスのカテゴリとチャンネル\n"
            "・各チャンネルの閲覧・発言権限\n"
            "・処罰ログ/歓迎メッセージ/チケットのスタッフロールなど、ボットの設定への反映",
            view=view, ephemeral=True,
        )
        timed_out = await view.wait()
        if timed_out or not view.confirmed:
            return

        guild = interaction.guild
        everyone = guild.default_role

        # ① スタッフロール
        staff_role = await self.get_or_create_role(
            guild, STAFF_ROLE_NAME,
            permissions=discord.Permissions(
                kick_members=True, ban_members=True, manage_messages=True,
                manage_channels=True, moderate_members=True, mention_everyone=True,
            ),
            color=discord.Color.blurple(),
            hoist=True,
        )

        # ② インフォメーション(閲覧のみ、発言はスタッフのみ)
        info_overwrites = {
            everyone: discord.PermissionOverwrite(view_channel=True, send_messages=False),
            staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        info_category = await self.get_or_create_category(guild, "📋 インフォメーション", info_overwrites)
        welcome_ch = await self.get_or_create_text(guild, "welcome", info_category, info_overwrites)
        announce_ch = await self.get_or_create_text(guild, "announcements", info_category, info_overwrites)
        rules_ch = await self.get_or_create_text(guild, "rules", info_category, info_overwrites)

        # ③ コミュニティ(誰でも閲覧・発言OK)
        community_overwrites = {
            everyone: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        community_category = await self.get_or_create_category(guild, "💬 コミュニティ", community_overwrites)
        general_ch = await self.get_or_create_text(guild, "general", community_category, community_overwrites)
        bot_ch = await self.get_or_create_text(guild, "bot-commands", community_category, community_overwrites)

        # ④ スタッフ専用(スタッフ以外は見えない)
        staff_overwrites = {
            everyone: discord.PermissionOverwrite(view_channel=False),
            staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        staff_category = await self.get_or_create_category(guild, "🛠️ スタッフ専用", staff_overwrites)
        staff_chat_ch = await self.get_or_create_text(guild, "staff-chat", staff_category, staff_overwrites)
        mod_log_ch = await self.get_or_create_text(guild, "mod-log", staff_category, staff_overwrites)

        # ⑤ ボイスチャンネル
        voice_overwrites = {
            everyone: discord.PermissionOverwrite(view_channel=True, connect=True),
        }
        voice_category = await self.get_or_create_category(guild, "🔊 ボイスチャンネル", voice_overwrites)
        await self.get_or_create_voice(guild, "雑談VC", voice_category, voice_overwrites)

        # ⑥ ボットの設定へ反映
        cfg.update_guild_config(
            guild.id,
            welcome_channel_id=welcome_ch.id,
            welcome_enabled=True,
            ticket_staff_role_id=staff_role.id,
            punish_log_channel_id=mod_log_ch.id,
            modlog_channel_id=mod_log_ch.id,
            modlog_enabled=True,
        )

        summary = (
            f"✅ セットアップが完了しました!\n\n"
            f"**作成/利用したロール**: {staff_role.mention}\n"
            f"**インフォメーション**: {welcome_ch.mention} {announce_ch.mention} {rules_ch.mention}\n"
            f"**コミュニティ**: {general_ch.mention} {bot_ch.mention}\n"
            f"**スタッフ専用**: {staff_chat_ch.mention} {mod_log_ch.mention}\n"
            f"**ボイス**: 雑談VC\n\n"
            f"処罰ログ・歓迎メッセージ(ON)・チケットのスタッフロールも、作成したチャンネル/ロールに自動設定しました。"
        )
        await interaction.followup.send(summary, ephemeral=True)
        await log_punishment(guild, interaction.user, "サーバー初期セットアップ実行", "/server_setup", interaction.user)

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
    await bot.add_cog(SetupCog(bot))
