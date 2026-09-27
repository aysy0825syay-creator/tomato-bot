"""
リンク許可リスト機能
- 登録したドメイン以外のURLを含むメッセージを自動削除する(荒らし対策の強化版)
"""
import json
import os
import re

import discord
from discord import app_commands
from discord.ext import commands

import config_manager as cfg

DATA_PATH = os.path.join(os.path.dirname(__file__), "linkfilter.json")
URL_PATTERN = re.compile(r"https?://([^\s/]+)")


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


class LinkFilterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        guild_cfg = cfg.get_guild_config(message.guild.id)
        if not guild_cfg["linkfilter_enabled"]:
            return
        if message.author.guild_permissions.manage_guild:
            return  # 管理者は対象外

        allowed = _load().get(str(message.guild.id), [])
        urls = URL_PATTERN.findall(message.content)
        for domain in urls:
            domain = domain.lower()
            if not any(domain == d or domain.endswith("." + d) for d in allowed):
                try:
                    await message.delete()
                except Exception:
                    pass
                try:
                    notice = await message.channel.send(
                        f"🔗 {message.author.mention} 許可されていないリンクが含まれていたため削除しました。"
                    )
                    await notice.delete(delay=6)
                except Exception:
                    pass
                return

    @app_commands.command(name="linkfilter_allow", description="許可するドメインを追加します")
    @app_commands.describe(domain="許可するドメイン(例: youtube.com)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def linkfilter_allow(self, interaction: discord.Interaction, domain: str):
        data = _load()
        key = str(interaction.guild_id)
        data.setdefault(key, [])
        domain = domain.lower().replace("https://", "").replace("http://", "").strip("/")
        if domain not in data[key]:
            data[key].append(domain)
            _save(data)
        await interaction.response.send_message(f"✅ 「{domain}」を許可リストに追加しました。", ephemeral=True)

    @app_commands.command(name="linkfilter_remove", description="許可リストからドメインを削除します")
    @app_commands.describe(domain="削除するドメイン")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def linkfilter_remove(self, interaction: discord.Interaction, domain: str):
        data = _load()
        key = str(interaction.guild_id)
        if domain in data.get(key, []):
            data[key].remove(domain)
            _save(data)
            await interaction.response.send_message(f"➖ 「{domain}」を許可リストから削除しました。", ephemeral=True)
        else:
            await interaction.response.send_message("そのドメインは登録されていません。", ephemeral=True)

    @app_commands.command(name="linkfilter_list", description="許可リストを表示します")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def linkfilter_list(self, interaction: discord.Interaction):
        domains = _load().get(str(interaction.guild_id), [])
        text = "、".join(domains) if domains else "(登録なし)"
        await interaction.response.send_message(f"📋 許可リスト: {text}", ephemeral=True)

    @app_commands.command(name="linkfilter_toggle", description="リンク許可リストの有効/無効を切り替えます")
    @app_commands.describe(enabled="有効にするならTrue、無効にするならFalse")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def linkfilter_toggle(self, interaction: discord.Interaction, enabled: bool):
        cfg.update_guild_config(interaction.guild_id, linkfilter_enabled=enabled)
        status = "有効" if enabled else "無効"
        await interaction.response.send_message(f"🔗 リンク許可リストを **{status}** にしました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LinkFilterCog(bot))
