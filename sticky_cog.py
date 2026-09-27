"""
固定メッセージ(スティッキーメッセージ)機能
- チャンネルの一番下に、常に同じ案内メッセージが表示され続けるようにする
"""
import json
import os

import discord
from discord import app_commands
from discord.ext import commands

DATA_PATH = os.path.join(os.path.dirname(__file__), "sticky.json")


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


class StickyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        data = _load()
        entry = data.get(str(message.channel.id))
        if not entry:
            return

        # 古い固定メッセージを削除してから、一番下に新しく投稿し直す
        old_id = entry.get("last_message_id")
        if old_id:
            try:
                old_msg = await message.channel.fetch_message(old_id)
                await old_msg.delete()
            except Exception:
                pass

        try:
            embed = discord.Embed(description=entry["text"], color=discord.Color.orange())
            embed.set_footer(text="📌 固定メッセージ")
            new_msg = await message.channel.send(embed=embed)
            entry["last_message_id"] = new_msg.id
            data[str(message.channel.id)] = entry
            _save(data)
        except Exception:
            pass

    @app_commands.command(name="sticky_set", description="このチャンネルに固定メッセージを設定します")
    @app_commands.describe(text="常に一番下に表示したい文章")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sticky_set(self, interaction: discord.Interaction, text: str):
        data = _load()
        embed = discord.Embed(description=text, color=discord.Color.orange())
        embed.set_footer(text="📌 固定メッセージ")
        msg = await interaction.channel.send(embed=embed)
        data[str(interaction.channel.id)] = {"text": text, "last_message_id": msg.id}
        _save(data)
        await interaction.response.send_message("📌 固定メッセージを設定しました。", ephemeral=True)

    @app_commands.command(name="sticky_remove", description="このチャンネルの固定メッセージを解除します")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sticky_remove(self, interaction: discord.Interaction):
        data = _load()
        entry = data.pop(str(interaction.channel.id), None)
        _save(data)
        if entry and entry.get("last_message_id"):
            try:
                old_msg = await interaction.channel.fetch_message(entry["last_message_id"])
                await old_msg.delete()
            except Exception:
                pass
        await interaction.response.send_message("🗑️ 固定メッセージを解除しました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(StickyCog(bot))
