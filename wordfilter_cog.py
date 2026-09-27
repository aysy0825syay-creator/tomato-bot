"""
NGワードフィルター機能
- 登録した単語を含むメッセージを自動削除する
"""
import json
import os

import discord
from discord import app_commands
from discord.ext import commands

import config_manager as cfg

DATA_PATH = os.path.join(os.path.dirname(__file__), "ngwords.json")


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


class WordFilterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        guild_cfg = cfg.get_guild_config(message.guild.id)
        if not guild_cfg["ngword_enabled"]:
            return
        words = _load().get(str(message.guild.id), [])
        if not words:
            return
        content_lower = message.content.lower()
        if any(w.lower() in content_lower for w in words):
            try:
                await message.delete()
            except Exception:
                pass
            try:
                notice = await message.channel.send(
                    f"🚫 {message.author.mention} のメッセージにNGワードが含まれていたため削除しました。"
                )
                await notice.delete(delay=6)
            except Exception:
                pass

    @app_commands.command(name="ngword_add", description="NGワードを追加します")
    @app_commands.describe(word="追加する単語")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ngword_add(self, interaction: discord.Interaction, word: str):
        data = _load()
        key = str(interaction.guild_id)
        data.setdefault(key, [])
        if word not in data[key]:
            data[key].append(word)
            _save(data)
        await interaction.response.send_message(f"➕ NGワードに「{word}」を追加しました。", ephemeral=True)

    @app_commands.command(name="ngword_remove", description="NGワードを削除します")
    @app_commands.describe(word="削除する単語")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ngword_remove(self, interaction: discord.Interaction, word: str):
        data = _load()
        key = str(interaction.guild_id)
        if word in data.get(key, []):
            data[key].remove(word)
            _save(data)
            await interaction.response.send_message(f"➖ NGワード「{word}」を削除しました。", ephemeral=True)
        else:
            await interaction.response.send_message("そのワードは登録されていません。", ephemeral=True)

    @app_commands.command(name="ngword_list", description="登録されているNGワード一覧を表示します")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ngword_list(self, interaction: discord.Interaction):
        words = _load().get(str(interaction.guild_id), [])
        text = "、".join(words) if words else "(登録なし)"
        await interaction.response.send_message(f"📋 NGワード一覧: {text}", ephemeral=True)

    @app_commands.command(name="ngword_toggle", description="NGワードフィルターの有効/無効を切り替えます")
    @app_commands.describe(enabled="有効にするならTrue、無効にするならFalse")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ngword_toggle(self, interaction: discord.Interaction, enabled: bool):
        cfg.update_guild_config(interaction.guild_id, ngword_enabled=enabled)
        status = "有効" if enabled else "無効"
        await interaction.response.send_message(f"🚫 NGワードフィルターを **{status}** にしました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(WordFilterCog(bot))
