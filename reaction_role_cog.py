"""
リアクションロール機能
- 特定メッセージに絵文字でリアクションすると、対応するロールが自動で付与/剥奪される
"""
import json
import os

import discord
from discord import app_commands
from discord.ext import commands

DATA_PATH = os.path.join(os.path.dirname(__file__), "reaction_roles.json")


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


class ReactionRoleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="reactionrole_add", description="メッセージに絵文字→ロールの組み合わせを登録します")
    @app_commands.describe(message_id="対象メッセージのID", emoji="使う絵文字", role="付与するロール")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reactionrole_add(self, interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
        data = _load()
        data.setdefault(message_id, {})
        data[message_id][emoji] = role.id
        _save(data)

        # 対象メッセージに絵文字をあらかじめ付けておく
        try:
            for channel in interaction.guild.text_channels:
                try:
                    msg = await channel.fetch_message(int(message_id))
                    await msg.add_reaction(emoji)
                    break
                except (discord.NotFound, discord.Forbidden):
                    continue
        except Exception:
            pass

        await interaction.response.send_message(
            f"✅ メッセージID {message_id} の {emoji} リアクションで {role.mention} を付与するよう設定しました。",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member is None or payload.member.bot:
            return
        data = _load()
        entry = data.get(str(payload.message_id))
        if not entry:
            return
        role_id = entry.get(str(payload.emoji))
        if not role_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        role = guild.get_role(role_id) if guild else None
        if role:
            try:
                await payload.member.add_roles(role, reason="リアクションロール")
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        data = _load()
        entry = data.get(str(payload.message_id))
        if not entry:
            return
        role_id = entry.get(str(payload.emoji))
        if not role_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        role = guild.get_role(role_id)
        member = guild.get_member(payload.user_id)
        if role and member:
            try:
                await member.remove_roles(role, reason="リアクションロール解除")
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRoleCog(bot))
