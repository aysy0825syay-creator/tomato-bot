"""
イベント/予定のリマインダー機能
- 指定した日時になったらお知らせする(ファイルに保存するので、ボット再起動をまたいでも消えない)
"""
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

DATA_PATH = os.path.join(os.path.dirname(__file__), "events.json")
JST = ZoneInfo("Asia/Tokyo")


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


class EventCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_events.start()

    def cog_unload(self):
        self.check_events.cancel()

    @tasks.loop(minutes=1)
    async def check_events(self):
        data = _load()
        now = datetime.now(timezone.utc)
        changed = False
        for event_id, event in list(data.items()):
            if event.get("notified"):
                continue
            event_time = datetime.fromisoformat(event["time"])
            if now >= event_time:
                channel = self.bot.get_channel(event["channel_id"])
                if channel:
                    try:
                        await channel.send(f"📅 予定のお知らせ:**{event['name']}** の時間になりました!")
                    except Exception:
                        pass
                event["notified"] = True
                changed = True
        if changed:
            _save(data)

    @check_events.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="event_add", description="指定した日時にお知らせする予定を登録します(日本時間)")
    @app_commands.describe(
        name="予定の名前",
        date="日付(例: 2026-10-01)",
        time="時刻(例: 19:00、24時間表記・日本時間)",
    )
    async def event_add(self, interaction: discord.Interaction, name: str, date: str, time: str):
        try:
            dt_jst = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=JST)
            dt_utc = dt_jst.astimezone(timezone.utc)
        except ValueError:
            await interaction.response.send_message(
                "⚠️ 日時の形式が正しくありません。例: date=2026-10-01 time=19:00", ephemeral=True
            )
            return

        data = _load()
        event_id = str(int(datetime.now().timestamp() * 1000))
        data[event_id] = {
            "guild_id": interaction.guild_id,
            "channel_id": interaction.channel_id,
            "name": name,
            "time": dt_utc.isoformat(),
            "notified": False,
        }
        _save(data)
        await interaction.response.send_message(
            f"📅 予定「{name}」を {date} {time}(日本時間)に登録しました。時間になったらこのチャンネルでお知らせします。"
        )

    @app_commands.command(name="event_list", description="登録されている予定の一覧を表示します")
    async def event_list(self, interaction: discord.Interaction):
        data = _load()
        lines = []
        for e in data.values():
            if e["guild_id"] != interaction.guild_id or e["notified"]:
                continue
            jst_time = datetime.fromisoformat(e["time"]).astimezone(JST)
            lines.append(f"・{e['name']}({jst_time.strftime('%Y-%m-%d %H:%M')} 日本時間)")
        text = "\n".join(lines) if lines else "登録されている予定はありません"
        await interaction.response.send_message(f"📅 予定一覧\n{text}")


async def setup(bot: commands.Bot):
    await bot.add_cog(EventCog(bot))
