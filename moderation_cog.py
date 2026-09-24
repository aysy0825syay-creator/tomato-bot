"""
緊急モデレーション機能
- /nuke_channels: サーバーの全チャンネルを削除する(荒らし対策の最終手段)
  誤爆防止のため「確認フレーズの入力」+「確認ボタン」の二重チェックを設けている
"""
import asyncio

import discord
from discord import app_commands
from discord.ext import commands

CONFIRM_PHRASE = "チャンネル全削除"


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=20)
        self.author_id = author_id
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "⚠️ このボタンはコマンドを実行した本人のみ使用できます。", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="本当に全チャンネルを削除する", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        await interaction.response.edit_message(content="🗑️ 削除を開始します…", view=None)

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        await interaction.response.edit_message(content="❌ キャンセルしました。", view=None)


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="nuke_channels",
        description="【危険】サーバーの全チャンネルを削除します(荒らし対策の最終手段)",
    )
    @app_commands.describe(confirm=f'確認のため "{CONFIRM_PHRASE}" と正確に入力してください')
    @app_commands.checks.has_permissions(administrator=True)
    async def nuke_channels(self, interaction: discord.Interaction, confirm: str):
        if confirm != CONFIRM_PHRASE:
            await interaction.response.send_message(
                f'⚠️ 確認フレーズが一致しません。"{CONFIRM_PHRASE}" と正確に入力してください。',
                ephemeral=True,
            )
            return

        view = ConfirmDeleteView(interaction.user.id)
        await interaction.response.send_message(
            "🚨 **本当にこのサーバーの全チャンネルを削除しますか?この操作は取り消せません。**",
            view=view,
            ephemeral=True,
        )
        timed_out = await view.wait()
        if timed_out or not view.confirmed:
            return

        guild = interaction.guild
        deleted = 0
        failed = 0
        for channel in list(guild.channels):
            try:
                await channel.delete(reason=f"{interaction.user} によるチャンネル全削除")
                deleted += 1
                await asyncio.sleep(0.5)  # レート制限を避けるための待機
            except Exception:
                failed += 1

        # サーバーが空にならないよう、案内用のチャンネルを1つ作成
        try:
            new_channel = await guild.create_text_channel("general")
            await new_channel.send(
                f"🍅 チャンネルの一括削除が完了しました。(削除: {deleted}件"
                + (f" / 失敗: {failed}件" if failed else "")
                + ")"
            )
        except Exception:
            pass

    @nuke_channels.error
    async def nuke_channels_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ このコマンドは「管理者」権限を持つメンバーのみ使用できます。", ephemeral=True
            )
        else:
            await interaction.response.send_message(f"❌ エラーが発生しました: {error}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
