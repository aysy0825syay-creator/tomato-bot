"""
荒らし対策(プロテクション)機能
- 新規アカウントの参加制限 / 大量参加(レイド)の自動検知
- チャンネルの大量作成・大量削除の自動検知(荒らしをBAN、作られたチャンネルを削除)
- メンションの乱用対策
- 無断でのBot追加の検知
- 緊急ロックダウン(/lockdown)

※ 監査ログを使うため、ボットには「監査ログの表示」権限が必要です。
"""
import asyncio
import json
import os
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

import config_manager as cfg
from punish_log import log_punishment

LOCKDOWN_PATH = os.path.join(os.path.dirname(__file__), "lockdown.json")

WINDOW = 10                # この秒数以内の連続行動を「大量」とみなす
NUKE_CREATE_LIMIT = 4      # WINDOW秒以内にチャンネルを何個作ったら荒らしとみなすか
NUKE_DELETE_LIMIT = 3      # WINDOW秒以内にチャンネルを何個消したら荒らしとみなすか
RAID_MODE_SECONDS = 300    # レイド検知後、新規参加を自動キックし続ける時間
PUNISH_MEMORY_SECONDS = 60 # 処罰後、この間に同じ人が作ったチャンネルは即削除


def _load_lock() -> dict:
    if not os.path.exists(LOCKDOWN_PATH):
        return {}
    with open(LOCKDOWN_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save_lock(data: dict) -> None:
    with open(LOCKDOWN_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class ProtectionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.join_times: dict[int, deque] = defaultdict(deque)   # guild_id -> [(time, member)]
        self.raid_until: dict[int, float] = {}                    # guild_id -> レイド対策モード終了時刻
        self.create_events: dict[tuple, list] = defaultdict(list) # (guild_id, user_id) -> [(time, channel_id)]
        self.delete_events: dict[tuple, list] = defaultdict(list)
        self.punished: dict[tuple, float] = {}                    # (guild_id, user_id) -> 処罰した時刻

    # ───────── 共通ヘルパー ─────────
    async def log(self, guild: discord.Guild, title: str, text: str, color=discord.Color.red()):
        channel_id = cfg.get_guild_config(guild.id)["protect_log_channel_id"]
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel is None:
            return
        try:
            embed = discord.Embed(title=title, description=text, color=color, timestamp=discord.utils.utcnow())
            await channel.send(embed=embed)
        except Exception:
            pass

    async def _kick(self, member: discord.Member, reason: str) -> bool:
        try:
            try:
                await member.send(f"「{member.guild.name}」の荒らし対策により、参加が制限されました。({reason})")
            except Exception:
                pass
            await member.kick(reason=f"荒らし対策: {reason}")
            await log_punishment(member.guild, member, "キック(自動)", reason)
            return True
        except Exception:
            return False

    async def _find_executor(self, guild: discord.Guild, action: discord.AuditLogAction, target_id: int):
        """監査ログから、その操作を実行した人を探す"""
        await asyncio.sleep(1)  # 監査ログへの反映を少し待つ
        try:
            async for entry in guild.audit_logs(limit=6, action=action):
                if getattr(entry.target, "id", None) == target_id:
                    return entry.user
        except discord.Forbidden:
            await self.log(
                guild, "⚠️ 権限が足りません",
                "監査ログを読めないため、荒らしを検知できません。\nボットのロールに「監査ログの表示」権限を付与してください。",
                discord.Color.orange(),
            )
        except Exception:
            pass
        return None

    async def _punish(self, guild: discord.Guild, user: discord.abc.User, reason: str, delete_ids: list[int]):
        """荒らしと判断した相手をBANし、作られたチャンネルを削除する"""
        deleted = 0
        for channel_id in delete_ids:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    await channel.delete(reason=f"荒らし対策: {reason}")
                    deleted += 1
                    await asyncio.sleep(0.3)
                except Exception:
                    pass

        result = ""
        punishment_label = "BAN(自動)"
        try:
            await guild.ban(user, reason=f"荒らし対策: {reason}")
            result = "✅ BANしました"
        except Exception:
            result = "❌ BANできませんでした(ボットのロールが相手より下、またはBAN権限がありません)"
            punishment_label = "ロール剥奪(自動・BAN失敗)"
            member = guild.get_member(user.id)
            if member:
                try:
                    await member.edit(roles=[], reason=f"荒らし対策: {reason}")
                    result += "\n代わりに、相手のロールをすべて外しました"
                except Exception:
                    pass
        await log_punishment(guild, user, punishment_label, reason)

        await self.log(
            guild, f"🚨 荒らしを検知: {reason}",
            f"実行者: {user} (ID: {user.id})\n{result}\n削除したチャンネル: {deleted}個",
        )

    # ───────── 参加時のチェック ─────────
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        if member.id == self.bot.user.id:
            return
        guild_cfg = cfg.get_guild_config(guild.id)

        if member.bot:
            if guild_cfg["protect_block_bots"]:
                await self._check_bot_add(member)
            return

        # 新規アカウントの制限
        min_days = guild_cfg["protect_min_account_days"]
        if min_days > 0:
            age_days = (discord.utils.utcnow() - member.created_at).days
            if age_days < min_days:
                await self._kick(member, f"アカウント作成から{age_days}日(基準: {min_days}日以上)")
                await self.log(
                    guild, "🚫 新規アカウントをキック",
                    f"{member} (ID: {member.id})\nアカウント作成から{age_days}日", discord.Color.orange(),
                )
                return

        # 大量参加(レイド)の検知
        limit = guild_cfg["protect_join_raid_limit"]
        if limit > 0:
            await self._check_join_raid(member, limit)

    async def _check_join_raid(self, member: discord.Member, limit: int):
        guild = member.guild
        now = time.time()

        if self.raid_until.get(guild.id, 0) > now:
            await self._kick(member, "荒らし対策モード中")
            return

        joins = self.join_times[guild.id]
        joins.append((now, member))
        while joins and now - joins[0][0] > WINDOW:
            joins.popleft()

        if len(joins) >= limit:
            self.raid_until[guild.id] = now + RAID_MODE_SECONDS
            victims = [m for _, m in joins]
            joins.clear()
            kicked = 0
            for m in victims:
                if await self._kick(m, "短時間の大量参加(レイドの疑い)"):
                    kicked += 1
            await self.log(
                guild, "🚨 大量参加(レイド)を検知",
                f"{WINDOW}秒以内に{len(victims)}人が参加しました。\n"
                f"{kicked}人をキックしました。今から{RAID_MODE_SECONDS // 60}分間は、新しく参加した人を自動でキックします。",
            )

    async def _check_bot_add(self, bot_member: discord.Member):
        """サーバーのオーナー以外がBotを追加した場合、そのBotをキックする"""
        guild = bot_member.guild
        adder = await self._find_executor(guild, discord.AuditLogAction.bot_add, bot_member.id)
        if adder is None:
            await self.log(
                guild, "⚠️ Botが追加されました",
                f"{bot_member} (ID: {bot_member.id})\n誰が追加したか特定できませんでした。心当たりがなければキックしてください。",
                discord.Color.orange(),
            )
            return
        if adder.id == guild.owner_id:
            await self.log(guild, "✅ オーナーがBotを追加", f"{bot_member} を追加したのは {adder} です。", discord.Color.green())
            return
        try:
            await bot_member.kick(reason=f"荒らし対策: オーナー以外({adder})によるBot追加")
            result = "✅ キックしました"
            await log_punishment(guild, bot_member, "キック(自動)", f"オーナー以外({adder})が追加したBot")
        except Exception:
            result = "❌ キックできませんでした(手動で対応してください)"
        await self.log(guild, "🚨 無断のBot追加を検知", f"Bot: {bot_member} (ID: {bot_member.id})\n追加した人: {adder} (ID: {adder.id})\n{result}")

    # ───────── チャンネルの大量作成・削除の検知 ─────────
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        if not cfg.get_guild_config(guild.id)["protect_anti_nuke"]:
            return
        executor = await self._find_executor(guild, discord.AuditLogAction.channel_create, channel.id)
        if executor is None or executor.id in (self.bot.user.id, guild.owner_id):
            return

        key = (guild.id, executor.id)
        now = time.time()

        # すでに処罰済みの相手が続けて作ったチャンネルは、その場で削除する
        if now - self.punished.get(key, 0) <= PUNISH_MEMORY_SECONDS:
            try:
                await channel.delete(reason="荒らし対策: 処罰済みユーザーが作成")
            except Exception:
                pass
            return

        events = [e for e in self.create_events[key] if now - e[0] <= WINDOW]
        events.append((now, channel.id))
        self.create_events[key] = events

        if len(events) >= NUKE_CREATE_LIMIT:
            self.punished[key] = now
            ids = [cid for _, cid in events]
            self.create_events[key] = []
            await self._punish(guild, executor, f"チャンネルの大量作成({len(ids)}個以上)", ids)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        if not cfg.get_guild_config(guild.id)["protect_anti_nuke"]:
            return
        executor = await self._find_executor(guild, discord.AuditLogAction.channel_delete, channel.id)
        if executor is None or executor.id in (self.bot.user.id, guild.owner_id):
            return

        key = (guild.id, executor.id)
        now = time.time()
        events = [e for e in self.delete_events[key] if now - e[0] <= WINDOW]
        events.append((now, channel.id))
        self.delete_events[key] = events

        if len(events) >= NUKE_DELETE_LIMIT and now - self.punished.get(key, 0) > PUNISH_MEMORY_SECONDS:
            self.punished[key] = now
            self.delete_events[key] = []
            await self._punish(guild, executor, f"チャンネルの大量削除({len(events)}個以上)", [])

    # ───────── メンションの乱用対策 ─────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        limit = cfg.get_guild_config(message.guild.id)["protect_mass_mention_limit"]
        if limit <= 0:
            return
        perms = message.author.guild_permissions
        if perms.administrator or perms.manage_messages:
            return

        count = len({m.id for m in message.mentions}) + len(message.role_mentions)
        if message.mention_everyone:
            count += 1
        if count >= limit:
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await message.author.timeout(discord.utils.utcnow() + timedelta(minutes=10), reason="荒らし対策: メンション乱用")
            except Exception:
                pass
            await self.log(
                message.guild, "🚫 メンション乱用を検知",
                f"{message.author} (ID: {message.author.id}) が1通で{count}件のメンションを送信。\nメッセージを削除し、10分間タイムアウトしました。",
                discord.Color.orange(),
            )
            await log_punishment(
                message.guild, message.author, "タイムアウト(10分) + メッセージ削除(自動)",
                f"1通に{count}件のメンションを送信",
            )

    # ───────── 緊急ロックダウン ─────────
    @app_commands.command(name="lockdown", description="【緊急】全テキストチャンネルで一般メンバーの発言を禁止します")
    @app_commands.checks.has_permissions(administrator=True)
    async def lockdown(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        data = _load_lock()
        saved = data.get(str(guild.id), {})
        changed = 0
        for channel in guild.text_channels:
            overwrite = channel.overwrites_for(guild.default_role)
            if str(channel.id) not in saved:
                saved[str(channel.id)] = overwrite.send_messages  # 元の設定を覚えておく
            overwrite.send_messages = False
            try:
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=f"{interaction.user} によるロックダウン")
                changed += 1
            except Exception:
                pass
            await asyncio.sleep(0.3)
        data[str(guild.id)] = saved
        _save_lock(data)
        await interaction.followup.send(f"🔒 {changed}個のチャンネルをロックしました。解除するには /unlockdown を使ってください。", ephemeral=True)
        await self.log(guild, "🔒 ロックダウン実行", f"{interaction.user} が全チャンネルをロックしました。", discord.Color.orange())

    @app_commands.command(name="unlockdown", description="ロックダウンを解除して、元の発言権限に戻します")
    @app_commands.checks.has_permissions(administrator=True)
    async def unlockdown(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        data = _load_lock()
        saved = data.get(str(guild.id))
        if not saved:
            await interaction.followup.send("今はロックダウン中ではありません。", ephemeral=True)
            return
        restored = 0
        for channel in guild.text_channels:
            if str(channel.id) not in saved:
                continue
            overwrite = channel.overwrites_for(guild.default_role)
            overwrite.send_messages = saved[str(channel.id)]
            try:
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=f"{interaction.user} がロックダウン解除")
                restored += 1
            except Exception:
                pass
            await asyncio.sleep(0.3)
        data.pop(str(guild.id), None)
        _save_lock(data)
        await interaction.followup.send(f"🔓 {restored}個のチャンネルを元に戻しました。", ephemeral=True)
        await self.log(guild, "🔓 ロックダウン解除", f"{interaction.user} がロックダウンを解除しました。", discord.Color.green())

    # ───────── 設定コマンド ─────────
    @app_commands.command(name="protect_log_channel", description="荒らし対策の通知を送るチャンネルを設定します")
    @app_commands.describe(channel="通知を送るチャンネル(スタッフ専用チャンネルがおすすめ)")
    @app_commands.checks.has_permissions(administrator=True)
    async def protect_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        cfg.update_guild_config(interaction.guild_id, protect_log_channel_id=channel.id)
        await interaction.response.send_message(f"📌 荒らし対策の通知先を {channel.mention} に設定しました。", ephemeral=True)

    @app_commands.command(name="protect_account_age", description="参加できるアカウントの最低経過日数を設定します(0で無効)")
    @app_commands.describe(days="アカウント作成から何日以上経っている人だけ参加OKにするか")
    @app_commands.checks.has_permissions(administrator=True)
    async def protect_account_age(self, interaction: discord.Interaction, days: int):
        days = max(0, min(days, 365))
        cfg.update_guild_config(interaction.guild_id, protect_min_account_days=days)
        text = f"{days}日未満のアカウントは自動でキックします。" if days else "無効にしました。"
        await interaction.response.send_message(f"🛡️ 新規アカウント制限: {text}", ephemeral=True)

    @app_commands.command(name="protect_join_raid", description="大量参加の検知人数を設定します(0で無効)")
    @app_commands.describe(limit=f"{WINDOW}秒以内に何人参加したら、レイドとみなすか(例: 5)")
    @app_commands.checks.has_permissions(administrator=True)
    async def protect_join_raid(self, interaction: discord.Interaction, limit: int):
        limit = max(0, min(limit, 50))
        cfg.update_guild_config(interaction.guild_id, protect_join_raid_limit=limit)
        text = f"{WINDOW}秒以内に{limit}人以上が参加したら、自動でキックします。" if limit else "無効にしました。"
        await interaction.response.send_message(f"🛡️ 大量参加の検知: {text}", ephemeral=True)

    @app_commands.command(name="protect_anti_nuke", description="チャンネル大量作成・削除の自動検知を切り替えます")
    @app_commands.describe(enabled="有効にするならTrue")
    @app_commands.checks.has_permissions(administrator=True)
    async def protect_anti_nuke(self, interaction: discord.Interaction, enabled: bool):
        cfg.update_guild_config(interaction.guild_id, protect_anti_nuke=enabled)
        status = "有効" if enabled else "無効"
        await interaction.response.send_message(f"🛡️ チャンネル大量作成・削除の検知を **{status}** にしました。", ephemeral=True)

    @app_commands.command(name="protect_mass_mention", description="メンション乱用の検知件数を設定します(0で無効)")
    @app_commands.describe(limit="1通に何件以上のメンションがあったら削除するか(例: 5)")
    @app_commands.checks.has_permissions(administrator=True)
    async def protect_mass_mention(self, interaction: discord.Interaction, limit: int):
        limit = max(0, min(limit, 50))
        cfg.update_guild_config(interaction.guild_id, protect_mass_mention_limit=limit)
        text = f"1通に{limit}件以上のメンションがあれば削除し、10分間タイムアウトします。" if limit else "無効にしました。"
        await interaction.response.send_message(f"🛡️ メンション乱用対策: {text}", ephemeral=True)

    @app_commands.command(name="protect_block_bots", description="オーナー以外によるBot追加の自動キックを切り替えます")
    @app_commands.describe(enabled="有効にするならTrue")
    @app_commands.checks.has_permissions(administrator=True)
    async def protect_block_bots(self, interaction: discord.Interaction, enabled: bool):
        cfg.update_guild_config(interaction.guild_id, protect_block_bots=enabled)
        status = "有効(サーバーのオーナー以外が追加したBotはキックします)" if enabled else "無効"
        await interaction.response.send_message(f"🛡️ 無断Bot追加の対策を **{status}** にしました。", ephemeral=True)

    @app_commands.command(name="protect_status", description="荒らし対策の現在の設定を確認します")
    @app_commands.checks.has_permissions(administrator=True)
    async def protect_status(self, interaction: discord.Interaction):
        c = cfg.get_guild_config(interaction.guild_id)
        log_ch = f"<#{c['protect_log_channel_id']}>" if c["protect_log_channel_id"] else "未設定"
        onoff = lambda v: "🟢 有効" if v else "⚪ 無効"
        embed = discord.Embed(title="🛡️ 荒らし対策の設定", color=discord.Color.blue())
        embed.add_field(name="通知チャンネル", value=log_ch, inline=False)
        embed.add_field(name="新規アカウント制限", value=f"{c['protect_min_account_days']}日未満をキック" if c["protect_min_account_days"] else "⚪ 無効")
        embed.add_field(name="大量参加の検知", value=f"{WINDOW}秒に{c['protect_join_raid_limit']}人" if c["protect_join_raid_limit"] else "⚪ 無効")
        embed.add_field(name="チャンネル大量作成・削除", value=onoff(c["protect_anti_nuke"]))
        embed.add_field(name="メンション乱用対策", value=f"{c['protect_mass_mention_limit']}件以上を削除" if c["protect_mass_mention_limit"] else "⚪ 無効")
        embed.add_field(name="無断Bot追加の対策", value=onoff(c["protect_block_bots"]))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "❌ このコマンドは「管理者」権限を持つメンバーのみ使用できます。"
        else:
            msg = f"❌ エラーが発生しました: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProtectionCog(bot))
