"""
認証パネル機能
- ボタン式 or リアクション式で、押す(反応する)と指定したロールが付与される
- 入室直後のメンバーへの「認証ゲート」として利用できる
"""
import json
import os

import discord
from discord import app_commands
from discord.ext import commands

DATA_PATH = os.path.join(os.path.dirname(__file__), "verify_panels.json")


def _load() -> dict:
    if not os.path.exists(DATA_PATH):
        return {}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save(data: dict) -> None:
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class VerifyButtonView(discord.ui.View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.role_id = role_id
        # custom_idにロールIDを埋め込み、再起動後も同じボタンとして機能させる
        button = discord.ui.Button(
            label="✅ 認証する",
            style=discord.ButtonStyle.success,
            custom_id=f"vexa_verify_{role_id}",
        )
        button.callback = self.on_click
        self.add_item(button)

    async def on_click(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if role is None:
            await interaction.response.send_message("⚠️ 設定されたロールが見つかりませんでした。", ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.response.send_message("すでに認証済みです。", ephemeral=True)
            return
        try:
            await interaction.user.add_roles(role, reason="認証パネルによる付与")
            await interaction.response.send_message(f"✅ 認証しました!{role.mention} を付与しました。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"⚠️ ロール付与に失敗しました: {e}", ephemeral=True)


class VerifyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # 再起動後もボタンを機能させるため、保存済みのボタン式パネルを再登録する
        data = _load()
        for entry in data.values():
            if entry.get("style") == "button":
                self.bot.add_view(VerifyButtonView(entry["role_id"]))

    @app_commands.command(name="verify_panel", description="認証パネルを設置します(ボタン式 or リアクション式)")
    @app_commands.describe(
        role="認証したメンバーに付与するロール",
        style="パネルの形式",
        emoji="リアクション式の場合に使う絵文字(既定: ✅)",
        message="パネルの説明文(省略可)",
    )
    @app_commands.choices(style=[
        app_commands.Choice(name="ボタン式", value="button"),
        app_commands.Choice(name="リアクション式", value="reaction"),
    ])
    @app_commands.checks.has_permissions(manage_roles=True)
    async def verify_panel(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        style: app_commands.Choice[str],
        emoji: str = "✅",
        message: str = "下のボタン(またはリアクション)を押すと認証され、サーバーを利用できるようになります。",
    ):
        embed = discord.Embed(title="⚡ メンバー認証", description=message, color=discord.Color.orange())

        if style.value == "button":
            view = VerifyButtonView(role.id)
            sent = await interaction.channel.send(embed=embed, view=view)
            data = _load()
            data[str(sent.id)] = {"style": "button", "role_id": role.id}
            _save(data)
            self.bot.add_view(view, message_id=sent.id)
        else:
            embed.description += f"\n\nリアクション: {emoji}"
            sent = await interaction.channel.send(embed=embed)
            try:
                await sent.add_reaction(emoji)
            except Exception:
                await interaction.response.send_message(
                    "⚠️ その絵文字は使用できませんでした。標準の絵文字か、このサーバーのカスタム絵文字を指定してください。",
                    ephemeral=True,
                )
                await sent.delete()
                return
            data = _load()
            data[str(sent.id)] = {"style": "reaction", "role_id": role.id, "emoji": emoji}
            _save(data)

        await interaction.response.send_message("✅ 認証パネルを設置しました。", ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member is None or payload.member.bot:
            return
        data = _load()
        entry = data.get(str(payload.message_id))
        if not entry or entry.get("style") != "reaction":
            return
        if str(payload.emoji) != entry.get("emoji"):
            return
        role = payload.member.guild.get_role(entry["role_id"])
        if role and role not in payload.member.roles:
            try:
                await payload.member.add_roles(role, reason="認証パネル(リアクション式)")
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(VerifyCog(bot))
