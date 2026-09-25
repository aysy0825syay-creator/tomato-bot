"""
実用ツール系コマンド
- 追加のAPIキー登録が不要な、無料の公開APIのみを使用しています
"""
import ast
import asyncio
import io
import operator
import secrets
import string
from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

# ───────── 安全な四則演算(/calc用) ─────────
_ALLOWED_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
    ast.FloorDiv: operator.floordiv,
}


def _safe_eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("使用できない記号が含まれています")


class UtilityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    # ───────── 計算機 ─────────
    @app_commands.command(name="calc", description="簡単な計算をします(例: (3+5)*2)")
    @app_commands.describe(expression="計算式")
    async def calc(self, interaction: discord.Interaction, expression: str):
        try:
            tree = ast.parse(expression, mode="eval")
            result = _safe_eval(tree.body)
            await interaction.response.send_message(f"🧮 {expression} = **{result}**")
        except Exception:
            await interaction.response.send_message("⚠️ 計算できませんでした。式を確認してください。", ephemeral=True)

    # ───────── 翻訳 ─────────
    @app_commands.command(name="translate", description="テキストを翻訳します")
    @app_commands.describe(text="翻訳したい文章", target_lang="翻訳先の言語コード(例: en, ja, ko, zh-CN)")
    async def translate(self, interaction: discord.Interaction, text: str, target_lang: str = "en"):
        await interaction.response.defer()
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": "auto", "tl": target_lang, "dt": "t", "q": text}
        try:
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
            translated = "".join(seg[0] for seg in data[0])
            await interaction.followup.send(f"🌐 ({target_lang}): {translated}")
        except Exception:
            await interaction.followup.send("⚠️ 翻訳に失敗しました。")

    # ───────── 天気 ─────────
    @app_commands.command(name="weather", description="指定した都市の天気を調べます")
    @app_commands.describe(city="都市名(例: Tokyo, Osaka, London)")
    async def weather(self, interaction: discord.Interaction, city: str):
        await interaction.response.defer()
        url = f"https://wttr.in/{city}"
        params = {"format": "j1"}
        try:
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
            cur = data["current_condition"][0]
            desc = cur["lang_ja"][0]["value"] if "lang_ja" in cur else cur["weatherDesc"][0]["value"]
            embed = discord.Embed(title=f"🌤️ {city} の天気", color=discord.Color.blue())
            embed.add_field(name="天気", value=desc)
            embed.add_field(name="気温", value=f"{cur['temp_C']}℃(体感 {cur['FeelsLikeC']}℃)")
            embed.add_field(name="湿度", value=f"{cur['humidity']}%")
            embed.add_field(name="風速", value=f"{cur['windspeedKmph']}km/h")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"⚠️ 天気情報を取得できませんでした。({type(e).__name__}: {e})")

    # ───────── 為替 ─────────
    @app_commands.command(name="currency", description="通貨を換算します")
    @app_commands.describe(amount="金額", from_currency="変換元の通貨コード(例: JPY)", to_currency="変換先の通貨コード(例: USD)")
    async def currency(self, interaction: discord.Interaction, amount: float, from_currency: str, to_currency: str):
        await interaction.response.defer()
        url = "https://api.frankfurter.app/latest"
        params = {"amount": amount, "from": from_currency.upper(), "to": to_currency.upper()}
        try:
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
            result = data["rates"][to_currency.upper()]
            await interaction.followup.send(
                f"💱 {amount} {from_currency.upper()} = **{result:.2f} {to_currency.upper()}**"
            )
        except Exception:
            await interaction.followup.send("⚠️ 換算に失敗しました。通貨コードを確認してください(例: JPY, USD, EUR)。")

    # ───────── 英単語辞書 ─────────
    @app_commands.command(name="define", description="英単語の意味を調べます")
    @app_commands.describe(word="調べたい英単語")
    async def define(self, interaction: discord.Interaction, word: str):
        await interaction.response.defer()
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    await interaction.followup.send("⚠️ その単語は見つかりませんでした。")
                    return
                data = await resp.json()
            meaning = data[0]["meanings"][0]
            definition = meaning["definitions"][0]["definition"]
            await interaction.followup.send(
                f"📖 **{word}**({meaning['partOfSpeech']})\n{definition}"
            )
        except Exception as e:
            await interaction.followup.send(f"⚠️ 意味を取得できませんでした。({type(e).__name__}: {e})")

    # ───────── QRコード生成 ─────────
    @app_commands.command(name="qrcode", description="テキストからQRコードを作成します")
    @app_commands.describe(text="QRコードにしたい文字列やURL")
    async def qrcode_cmd(self, interaction: discord.Interaction, text: str):
        await interaction.response.defer()
        try:
            import qrcode
            img = qrcode.make(text)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            await interaction.followup.send(file=discord.File(buf, filename="qrcode.png"))
        except Exception as e:
            await interaction.followup.send(f"⚠️ QRコードの作成に失敗しました: {e}")

    # ───────── パスワード生成 ─────────
    @app_commands.command(name="password", description="ランダムなパスワードを生成します")
    @app_commands.describe(length="文字数(既定:16)")
    async def password(self, interaction: discord.Interaction, length: int = 16):
        length = max(8, min(length, 64))
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        pw = "".join(secrets.choice(chars) for _ in range(length))
        await interaction.response.send_message(f"🔑 生成したパスワード(本人にのみ表示): ||{pw}||", ephemeral=True)

    # ───────── 世界時計 ─────────
    @app_commands.command(name="worldtime", description="指定した地域の現在時刻を調べます")
    @app_commands.describe(timezone="タイムゾーン名(例: Asia/Tokyo, America/New_York, Europe/London)")
    async def worldtime(self, interaction: discord.Interaction, timezone: str):
        if timezone not in available_timezones():
            await interaction.response.send_message(
                "⚠️ そのタイムゾーン名は見つかりません。例: Asia/Tokyo, America/New_York, Europe/London", ephemeral=True
            )
            return
        now = datetime.now(ZoneInfo(timezone))
        await interaction.response.send_message(f"🕐 {timezone} の現在時刻: **{now.strftime('%Y-%m-%d %H:%M:%S')}**")

    # ───────── Wikipedia検索 ─────────
    @app_commands.command(name="wiki", description="Wikipediaで検索して要約を表示します")
    @app_commands.describe(query="調べたいキーワード")
    async def wiki(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        url = f"https://ja.wikipedia.org/api/rest_v1/page/summary/{query}"
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    await interaction.followup.send("⚠️ その項目は見つかりませんでした。")
                    return
                data = await resp.json()
            embed = discord.Embed(
                title=data.get("title", query),
                description=data.get("extract", "説明がありません"),
                url=data.get("content_urls", {}).get("desktop", {}).get("page"),
                color=discord.Color.teal(),
            )
            thumb = data.get("thumbnail", {}).get("source")
            if thumb:
                embed.set_thumbnail(url=thumb)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"⚠️ 検索に失敗しました。({type(e).__name__}: {e})")


async def setup(bot: commands.Bot):
    await bot.add_cog(UtilityCog(bot))
