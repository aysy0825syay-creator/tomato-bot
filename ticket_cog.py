"""
チケットシステム機能
- ボタンを押すと、本人とスタッフだけが見られる専用チャンネルが自動作成される
"""
import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta

import config_manager as cfg


class TicketOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # 常時有効なボタン

    @discord.ui.button(label="🎫 チケットを作成", style=discord.ButtonStyle.primary, custom_id="tomato_ticket_open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        guild_cfg = cfg.get_guild_config(guild.id)

        # すでに本人のチケットが存在するかチェック
        existing = discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.name}".lower())
        if existing:
            await interaction.response.send_message(f"すでにチケットがあります: {existing.mention}", ephemeral=True)
            return

        category = guild.get_channel(guild_cfg["ticket_category_id"]) if guild_cfg["ticket_category_id"] else None
        staff_role = guild.get_role(guild_cfg["ticket_staff_role_id"]) if guild_cfg["ticket_staff_role_id"] else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        channel = await guild.create_text_channel(
            f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites,
            reason=f"{interaction.user} のチケット作成",
        )
        await interaction.response.send_message(f"🎫 チケットを作成しました: {channel.mention}", ephemeral=True)
        await channel.send(
            f"🍅 {interaction.user.mention} さん、お問い合わせありがとうございます!\n"
            f"ここでスタッフに相談できます。解決したら下のボタンでチケットを閉じてください。",
            view=TicketCloseView(),
        )


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 チケットを閉じる", style=discord.ButtonStyle.danger, custom_id="tomato_ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("このチケットを5秒後に閉じます…")
        await interaction.channel.send("🔒 チケットをクローズします。")
        await discord.utils.sleep_until(discord.utils.utcnow() + timedelta(seconds=5))
        await interaction.channel.delete(reason=f"{interaction.user} がチケットを閉じました")


class TicketCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 再起動後もボタンが効くように、永続Viewとして登録
        bot.add_view(TicketOpenView())
        bot.add_view(TicketCloseView())

    @app_commands.command(name="ticket_panel", description="チケット作成用のパネルを設置します")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🍅 お問い合わせ",
            description="スタッフに個別に相談したいときは、下のボタンを押してください。\nあなたとスタッフだけが見られる専用チャンネルが作成されます。",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, view=TicketOpenView())

    @app_commands.command(name="ticket_category", description="チケットチャンネルを作るカテゴリを設定します")
    @app_commands.describe(category="使用するカテゴリ")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_category(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        cfg.update_guild_config(interaction.guild_id, ticket_category_id=category.id)
        await interaction.response.send_message(f"📁 チケットカテゴリを「{category.name}」に設定しました。", ephemeral=True)

    @app_commands.command(name="ticket_staff_role", description="チケットを見られるスタッフロールを設定します")
    @app_commands.describe(role="スタッフロール")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_staff_role(self, interaction: discord.Interaction, role: discord.Role):
        cfg.update_guild_config(interaction.guild_id, ticket_staff_role_id=role.id)
        await interaction.response.send_message(f"🧑‍💼 チケット対応スタッフロールを {role.mention} に設定しました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketCog(bot))
