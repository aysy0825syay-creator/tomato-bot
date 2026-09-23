"""
Discord ボット本体
- 入退室ログ機能(サーバーごとにON/OFF、チャンネル指定可)
- AI応答機能(Claude APIを使用、指定チャンネルでの会話に応答)
"""
import os
import datetime
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from groq import Groq

import config_manager as cfg

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
AI_MODEL = "llama-3.1-8b-instant"  # 使用するAIモデル(Groqの無料枠モデル)
HISTORY_LIMIT = 20  # チャンネルごとに保持する会話履歴の件数

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN が設定されていません。.env を確認してください。")

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

intents = discord.Intents.default()
intents.members = True          # 入退室イベントを受け取るために必要
intents.message_content = True  # メッセージ内容を読むために必要

bot = commands.Bot(command_prefix="!", intents=intents)

# チャンネルIDごとの会話履歴 (role, content) を保持
conversation_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))


# ─────────────────────────────
# 起動時処理
# ─────────────────────────────
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンドを {len(synced)} 件同期しました。")
    except Exception as e:
        print(f"コマンド同期に失敗しました: {e}")
    print(f"ログイン完了: {bot.user} (ID: {bot.user.id})")


# ─────────────────────────────
# 入室ログ
# ─────────────────────────────
@bot.event
async def on_member_join(member: discord.Member):
    guild_cfg = cfg.get_guild_config(member.guild.id)
    if not guild_cfg["log_enabled"] or not guild_cfg["join_channel_id"]:
        return

    channel = member.guild.get_channel(guild_cfg["join_channel_id"])
    if channel is None:
        return

    embed = discord.Embed(
        title="✅ メンバー入室",
        description=f"{member.mention} さんがサーバーに参加しました。",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ユーザー", value=f"{member} (ID: {member.id})", inline=False)
    embed.add_field(name="現在のメンバー数", value=str(member.guild.member_count), inline=False)
    await channel.send(embed=embed)


# ─────────────────────────────
# 退室ログ
# ─────────────────────────────
@bot.event
async def on_member_remove(member: discord.Member):
    guild_cfg = cfg.get_guild_config(member.guild.id)
    if not guild_cfg["log_enabled"] or not guild_cfg["leave_channel_id"]:
        return

    channel = member.guild.get_channel(guild_cfg["leave_channel_id"])
    if channel is None:
        return

    embed = discord.Embed(
        title="❌ メンバー退室",
        description=f"{member} さんがサーバーから退室しました。",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ユーザー", value=f"{member} (ID: {member.id})", inline=False)
    embed.add_field(name="現在のメンバー数", value=str(member.guild.member_count), inline=False)
    await channel.send(embed=embed)


# ─────────────────────────────
# AI応答
# ─────────────────────────────
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return

    guild_cfg = cfg.get_guild_config(message.guild.id)
    if (
        guild_cfg["ai_enabled"]
        and guild_cfg["ai_channel_id"] == message.channel.id
        and message.content.strip()
    ):
        await handle_ai_response(message)

    # プレフィックスコマンド(!から始まるもの)も処理できるようにする
    await bot.process_commands(message)


SYSTEM_PROMPT = (
    "あなたはDiscordサーバーで会話するフレンドリーなアシスタントです。"
    "自然な日本語で、簡潔かつ親しみやすく応答してください。"
)


async def handle_ai_response(message: discord.Message):
    if groq_client is None:
        await message.channel.send(
            "⚠️ GROQ_API_KEY が設定されていないため、AI応答を利用できません。"
        )
        return

    history = conversation_history[message.channel.id]
    history.append({"role": "user", "content": message.content})

    async with message.channel.typing():
        try:
            response = groq_client.chat.completions.create(
                model=AI_MODEL,
                max_tokens=1000,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + list(history),
            )
            reply_text = (response.choices[0].message.content or "").strip()
        except Exception as e:
            await message.channel.send(f"⚠️ AI応答中にエラーが発生しました: {e}")
            return

    if not reply_text:
        reply_text = "(応答を生成できませんでした)"

    history.append({"role": "assistant", "content": reply_text})

    # Discordのメッセージは2000文字制限があるため分割して送信
    for i in range(0, len(reply_text), 2000):
        await message.channel.send(reply_text[i : i + 2000])


# ─────────────────────────────
# スラッシュコマンド: ログ設定
# ─────────────────────────────
@bot.tree.command(name="log_toggle", description="入退室ログの有効/無効を切り替えます")
@app_commands.describe(enabled="有効にするならTrue、無効にするならFalse")
@app_commands.checks.has_permissions(manage_guild=True)
async def log_toggle(interaction: discord.Interaction, enabled: bool):
    cfg.update_guild_config(interaction.guild_id, log_enabled=enabled)
    status = "有効" if enabled else "無効"
    await interaction.response.send_message(f"📋 入退室ログを **{status}** にしました。", ephemeral=True)


@bot.tree.command(name="log_channel", description="入室ログ or 退室ログのチャンネルを設定します")
@app_commands.describe(種類="join(入室) または leave(退室)", channel="ログを送るチャンネル")
@app_commands.choices(種類=[
    app_commands.Choice(name="入室ログ", value="join"),
    app_commands.Choice(name="退室ログ", value="leave"),
])
@app_commands.checks.has_permissions(manage_guild=True)
async def log_channel(interaction: discord.Interaction, 種類: app_commands.Choice[str], channel: discord.TextChannel):
    key = "join_channel_id" if 種類.value == "join" else "leave_channel_id"
    cfg.update_guild_config(interaction.guild_id, **{key: channel.id})
    label = "入室ログ" if 種類.value == "join" else "退室ログ"
    await interaction.response.send_message(
        f"📌 {label}のチャンネルを {channel.mention} に設定しました。", ephemeral=True
    )


# ─────────────────────────────
# スラッシュコマンド: AI設定
# ─────────────────────────────
@bot.tree.command(name="ai_toggle", description="AI応答の有効/無効を切り替えます")
@app_commands.describe(enabled="有効にするならTrue、無効にするならFalse")
@app_commands.checks.has_permissions(manage_guild=True)
async def ai_toggle(interaction: discord.Interaction, enabled: bool):
    cfg.update_guild_config(interaction.guild_id, ai_enabled=enabled)
    status = "有効" if enabled else "無効"
    await interaction.response.send_message(f"🤖 AI応答を **{status}** にしました。", ephemeral=True)


@bot.tree.command(name="ai_channel", description="AIが応答するチャンネルを設定します")
@app_commands.describe(channel="AIが応答するチャンネル")
@app_commands.checks.has_permissions(manage_guild=True)
async def ai_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg.update_guild_config(interaction.guild_id, ai_channel_id=channel.id)
    conversation_history.pop(channel.id, None)  # チャンネル変更時は履歴をリセット
    await interaction.response.send_message(
        f"📌 AI応答チャンネルを {channel.mention} に設定しました。", ephemeral=True
    )


@bot.tree.command(name="ai_reset", description="現在のチャンネルのAI会話履歴をリセットします")
@app_commands.checks.has_permissions(manage_guild=True)
async def ai_reset(interaction: discord.Interaction):
    conversation_history.pop(interaction.channel_id, None)
    await interaction.response.send_message("🔄 会話履歴をリセットしました。", ephemeral=True)


@bot.tree.command(name="settings", description="現在のサーバー設定を確認します")
async def settings(interaction: discord.Interaction):
    guild_cfg = cfg.get_guild_config(interaction.guild_id)
    join_ch = f"<#{guild_cfg['join_channel_id']}>" if guild_cfg["join_channel_id"] else "未設定"
    leave_ch = f"<#{guild_cfg['leave_channel_id']}>" if guild_cfg["leave_channel_id"] else "未設定"
    ai_ch = f"<#{guild_cfg['ai_channel_id']}>" if guild_cfg["ai_channel_id"] else "未設定"

    embed = discord.Embed(title="⚙️ 現在の設定", color=discord.Color.blurple())
    embed.add_field(name="入退室ログ", value="有効" if guild_cfg["log_enabled"] else "無効", inline=True)
    embed.add_field(name="入室ログch", value=join_ch, inline=True)
    embed.add_field(name="退室ログch", value=leave_ch, inline=True)
    embed.add_field(name="AI応答", value="有効" if guild_cfg["ai_enabled"] else "無効", inline=True)
    embed.add_field(name="AI応答ch", value=ai_ch, inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# 権限エラーのハンドリング(共通)
@log_toggle.error
@log_channel.error
@ai_toggle.error
@ai_channel.error
@ai_reset.error
async def on_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ このコマンドを使うには「サーバー管理」権限が必要です。", ephemeral=True
        )
    else:
        await interaction.response.send_message(f"❌ エラーが発生しました: {error}", ephemeral=True)


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
