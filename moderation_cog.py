"""
緊急モデレーション機能
- /nuke_channels: サーバーの全チャンネルを削除する(荒らし対策の最終手段)
  誤爆防止のため「確認フレーズの入力」+「確認ボタン」の二重チェックを設けている
- /warn /warnings /kick /ban /timeout: 基本的なモデレーションコマンド
- /backup_channels: 今のチャンネル構成をテキストで書き出す(荒らし対策の事前準備)
"""
import asyncio
import json
import os
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

CONFIRM_PHRASE = "チャンネル全削除"
WARN_PATH = os.path.join(os.path.dirname(__file__), "warns.json")


def _load_warns() -> dict:
    if not os.path.exists(WARN_PATH):
        return {}
    with open(WARN_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save_warns(data: dict) -> None:
    with open(WARN_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_warn(guild_id: int, user_id: int, reason: str, moderator: str) -> int:
    data = _load_warns()
    key = f"{guild_id}:{user_id}"
    data.setdefault(key, [])
    data[key].append({"reason": reason, "by": moderator})
    _save_warns(data)
    return len(data[key])


def get_warns(guild_id: int, user_id: int) -> list:
    return _load_warns().get(f"{guild_id}:{user_id}", [])


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

    # ───────── 警告 ─────────
    @app_commands.command(name="warn", description="メンバーに警告を出します")
    @app_commands.describe(user="警告するユーザー", reason="理由")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        count = add_warn(interaction.guild_id, user.id, reason, str(interaction.user))
        await interaction.response.send_message(
            f"⚠️ {user.mention} に警告しました(通算{count}回目)\n理由: {reason}"
        )

    @app_commands.command(name="warnings", description="メンバーの警告履歴を確認します")
    @app_commands.describe(user="確認するユーザー")
    async def warnings(self, interaction: discord.Interaction, user: discord.Member):
        warns = get_warns(interaction.guild_id, user.id)
        if not warns:
            await interaction.response.send_message(f"{user.display_name} に警告履歴はありません")
            return
        lines = [f"{i+1}. {w['reason']}(by {w['by']})" for i, w in enumerate(warns)]
        await interaction.response.send_message(
            f"⚠️ {user.display_name} の警告履歴({len(warns)}件)\n" + "\n".join(lines)
        )

    # ───────── キック ─────────
    @app_commands.command(name="kick", description="メンバーをキックします")
    @app_commands.describe(user="キックするユーザー", reason="理由")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str = "理由なし"):
        await user.kick(reason=f"{interaction.user}: {reason}")
        await interaction.response.send_message(f"👢 {user.display_name} をキックしました\n理由: {reason}")

    # ───────── BAN ─────────
    @app_commands.command(name="ban", description="メンバーをBANします")
    @app_commands.describe(user="BANするユーザー", reason="理由")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = "理由なし"):
        await user.ban(reason=f"{interaction.user}: {reason}")
        await interaction.response.send_message(f"🔨 {user.display_name} をBANしました\n理由: {reason}")

    # ───────── タイムアウト ─────────
    @app_commands.command(name="timeout", description="メンバーを一時的にタイムアウトします")
    @app_commands.describe(user="対象ユーザー", minutes="タイムアウトする分数", reason="理由")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, user: discord.Member, minutes: int, reason: str = "理由なし"):
        minutes = max(1, min(minutes, 40320))  # 上限28日
        until = discord.utils.utcnow() + timedelta(minutes=minutes)
        await user.timeout(until, reason=f"{interaction.user}: {reason}")
        await interaction.response.send_message(
            f"🔇 {user.display_name} を{minutes}分間タイムアウトしました\n理由: {reason}"
        )

    # ───────── チャンネル構成バックアップ ─────────
    @app_commands.command(name="backup_channels", description="今のチャンネル構成をテキストで書き出します")
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_channels(self, interaction: discord.Interaction):
        guild = interaction.guild
        lines = []
        for category in [None] + list(guild.categories):
            cat_name = category.name if category else "(カテゴリなし)"
            channels = [c for c in guild.channels if getattr(c, "category", None) == category and not isinstance(c, discord.CategoryChannel)]
            if not channels and category is None:
                continue
            lines.append(f"\n📁 {cat_name}")
            for ch in channels:
                kind = "🔊" if isinstance(ch, discord.VoiceChannel) else "#"
                lines.append(f"  {kind} {ch.name}")
        text = "\n".join(lines) if lines else "(チャンネルがありません)"
        # 2000文字制限があるため必要に応じて分割
        await interaction.response.send_message(f"📋 **{guild.name} のチャンネル構成バックアップ**")
        for i in range(0, len(text), 1900):
            await interaction.followup.send(f"```{text[i:i+1900]}```")


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
