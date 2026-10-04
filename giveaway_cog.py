"""
抽選(ギブアウェイ)機能
"""
import asyncio
import random

import discord
from discord import app_commands
from discord.ext import commands

GIVEAWAY_EMOJI = "🎉"


class GiveawayCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="giveaway", description="抽選(ギブアウェイ)を開催します")
    @app_commands.describe(prize="景品の内容", minutes="何分後に抽選するか", winners="当選人数(既定:1)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway(self, interaction: discord.Interaction, prize: str, minutes: int, winners: int = 1):
        minutes = max(1, min(minutes, 10080))  # 上限7日
        winners = max(1, min(winners, 20))

        embed = discord.Embed(
            title="🎉 ギブアウェイ開催!",
            description=f"**景品:{prize}**\n\n{GIVEAWAY_EMOJI} のリアクションで応募!\n当選人数: {winners}名\n"
                        f"終了まで: 約{minutes}分",
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        await message.add_reaction(GIVEAWAY_EMOJI)

        async def _job():
            await asyncio.sleep(minutes * 60)
            try:
                fresh = await interaction.channel.fetch_message(message.id)
            except Exception:
                return
            reaction = discord.utils.get(fresh.reactions, emoji=GIVEAWAY_EMOJI)
            entrants = []
            if reaction:
                async for user in reaction.users():
                    if not user.bot:
                        entrants.append(user)

            if not entrants:
                await interaction.channel.send(f"🎉「{prize}」の抽選には誰も参加していませんでした…")
                return

            picked = random.sample(entrants, min(winners, len(entrants)))
            mentions = "、".join(u.mention for u in picked)
            await interaction.channel.send(f"🎉 抽選結果!「{prize}」の当選者は… {mentions} さんです!おめでとうございます⚡")

        self.bot.loop.create_task(_job())


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayCog(bot))
