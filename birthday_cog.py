"""
誕生日登録 & お祝い通知機能
- 毎日決まった時刻に、今日が誕生日のメンバーがいないかチェックしてお祝いする
"""
import json
import os
from datetime import datetime, time as dtime

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config_manager as cfg

DATA_PATH = os.path.join(os.path.dirname(__file__), "birthdays.json")
CHECK_TIME = dtime(hour=0, minute=5)  # 毎日 0:05 (UTC)にチェック


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


class BirthdayCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_birthdays.start()

    def cog_unload(self):
        self.check_birthdays.cancel()

    @tasks.loop(time=CHECK_TIME)
    async def check_birthdays(self):
        today = datetime.utcnow().strftime("%m-%d")
        data = _load()
        for guild in self.bot.guilds:
            guild_cfg = cfg.get_guild_config(guild.id)
            if not guild_cfg["birthday_channel_id"]:
                continue
            channel = guild.get_channel(guild_cfg["birthday_channel_id"])
            if channel is None:
                continue
            entries = data.get(str(guild.id), {})
            for user_id, md in entries.items():
                if md == today:
                    member = guild.get_member(int(user_id))
                    if member:
                        await channel.send(f"🎂🍅 {member.mention} さん、お誕生日おめでとうございます!🎉")

    @check_birthdays.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="birthday_set", description="自分の誕生日を登録します")
    @app_commands.describe(month="誕生月(1〜12)", day="誕生日(1〜31)")
    async def birthday_set(self, interaction: discord.Interaction, month: int, day: int):
        if not (1 <= month <= 12 and 1 <= day <= 31):
            await interaction.response.send_message("⚠️ 正しい月日を入力してください。", ephemeral=True)
            return
        data = _load()
        key = str(interaction.guild_id)
        data.setdefault(key, {})
        data[key][str(interaction.user.id)] = f"{month:02d}-{day:02d}"
        _save(data)
        await interaction.response.send_message(f"🎂 誕生日を {month}月{day}日 として登録しました!", ephemeral=True)

    @app_commands.command(name="birthday_channel", description="誕生日お祝いを投稿するチャンネルを設定します")
    @app_commands.describe(channel="投稿先チャンネル")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def birthday_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        cfg.update_guild_config(interaction.guild_id, birthday_channel_id=channel.id)
        await interaction.response.send_message(f"📌 誕生日通知チャンネルを {channel.mention} に設定しました。", ephemeral=True)

    @app_commands.command(name="birthday_list", description="今月誕生日のメンバー一覧を表示します")
    async def birthday_list(self, interaction: discord.Interaction):
        data = _load().get(str(interaction.guild_id), {})
        this_month = datetime.utcnow().strftime("%m")
        lines = []
        for user_id, md in data.items():
            if md.startswith(this_month):
                member = interaction.guild.get_member(int(user_id))
                if member:
                    lines.append(f"{md[3:]}日: {member.display_name}")
        text = "\n".join(sorted(lines)) if lines else "今月は登録者がいません"
        await interaction.response.send_message(f"🎂 今月の誕生日一覧\n{text}")


async def setup(bot: commands.Bot):
    await bot.add_cog(BirthdayCog(bot))
